# -*- coding: utf-8 -*-
"""深交所逐笔数据的订单簿重建。

核心思想只有三条：
    委托流里的「限价单」→ 进簿
    成交流里的 ExecType='4' → 扣减买卖双方的剩余量
    成交流里的 ExecType='F' → 按委托号删除（这就是「撤单」）

为什么撤单在成交流里？因为深交所的逐笔委托只发「新订单」，
撤单是作为一种「执行事件」发在成交流里的（ExecType='F'）。
这一点如果不看接口规范，光靠猜是猜不到的。
"""
import pandas as pd

from book import OrderBook


class SZRebooker:
    """把逐笔委托 + 逐笔成交 合并成一条事件流，逐条重放出订单簿。"""

    def __init__(self):
        self.book = OrderBook()
        self.event_count = 0
        self.miss = {"order": 0, "trade": 0, "cancel": 0}
        # 记账：用来做「守恒校验」——进簿量 − 成交量 − 撤单量 应该等于期末剩余量
        self.stats = {"added": 0.0, "traded": 0.0, "cancelled": 0.0}
        self.snap_times = []      # 需要打点的时刻（来自官方快照的时间轴）
        self.records = []         # [(时刻, 重建出来的盘口)]
        self.ignore_cancel = False  # 教学开关：打开后故意忽略撤单，用来看校验器能不能抓到错

    # ------------------------------------------------------------------
    def on_order(self, m):
        """处理一笔逐笔委托。"""
        seq = int(m["ApplSeqNum"])
        raw_side = str(m["Side"])
        # 深交所：1=买 2=卖。有些数据商直接给 B/S，这里两种都兼容。
        side = "B" if raw_side in ("1", "B", "b") else "S"
        otype = str(m["OrdType"])
        price = float(m["Price"])
        qty = float(m["OrderQty"])

        if otype == "1":                      # 市价单：立即成交，不留在簿里
            return
        if otype == "3":                      # 本方最优：价格取同侧最优价
            best = self.book.best(side, 1)
            if not best:
                self.miss["order"] += 1
                return
            price = best[0][0]
        self.book.add(seq, side, round(price, 2), qty)
        self.stats["added"] += qty

    # ------------------------------------------------------------------
    def on_trade(self, m):
        """处理一笔逐笔成交（成交或撤单）。"""
        if str(m["ExecType"]) == "4":
            qty = float(m["TradeQty"])
            bid = int(m["BidApplSeqNum"])
            ask = int(m["AskApplSeqNum"])
            got_b = self.book.reduce(bid, qty)
            got_s = self.book.reduce(ask, qty)
            self.stats["traded"] += got_b + got_s
            # 只有「两侧都没扣到」才是异常：市价单本身就是一侧扣不到，属正常
            if got_b == 0 and got_s == 0:
                self.miss["trade"] += 1
        elif str(m["ExecType"]) == "F":
            if self.ignore_cancel:            # 故意不做，用来演示「漏掉撤单会怎样」
                return
            qty = float(m["TradeQty"])
            sid = int(m["BidApplSeqNum"]) or int(m["AskApplSeqNum"])
            got = self.book.reduce(sid, qty)
            self.stats["cancelled"] += got
            if got == 0:
                self.miss["cancel"] += 1

    # ------------------------------------------------------------------
    def run(self, orders: pd.DataFrame, trades: pd.DataFrame, snap_times=None, snap_seqs=None,
            capture_before=False):
        """按 (ChannelNo, ApplSeqNum) 排序合并两路消息，逐条应用。

        打点有两种方式：
        - snap_seqs：在「处理完第 N 条消息」之后拍一张，用于和官方快照精确比对；
        - snap_times：在「时间跨过 T」时拍一张，等价于「T 时刻的簿」，用于做因子。

        capture_before：官方快照是在 T 时刻「这一批事件处理之前」拍的，还是之后拍的？
        不同数据商的约定不一样，用校验结果决定（True = 严格早于 T 的事件才算进去）。
        """
        ev = pd.concat([orders.assign(evt="O"), trades.assign(evt="T")], ignore_index=True)
        ev = ev.sort_values(["ChannelNo", "ApplSeqNum"], kind="stable")

        seqs = sorted(snap_seqs or [])
        times = sorted(snap_times or [])
        pi = pj = 0

        for row in ev.itertuples(index=False):
            self.event_count += 1
            seq, t = int(row.ApplSeqNum), row.TransactTime

            while pj < len(times) and (t >= times[pj] if capture_before else t > times[pj]):
                self.records.append((times[pj], self.book.snapshot(10)))
                pj += 1

            if row.evt == "O":
                self.on_order(row._asdict())
            else:
                self.on_trade(row._asdict())

            while pi < len(seqs) and seq >= seqs[pi]:
                self.records.append((seq, self.book.snapshot(10)))
                pi += 1

        while pi < len(seqs):
            self.records.append((seqs[pi], self.book.snapshot(10)))
            pi += 1
        while pj < len(times):
            self.records.append((times[pj], self.book.snapshot(10)))
            pj += 1
        return self

