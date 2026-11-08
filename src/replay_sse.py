# -*- coding: utf-8 -*-
"""沪市重建：两种模式。

模式 A：有逐笔委托（成交里可能没有委托号）
    → 靠「价格 + 时间优先」在本地队列里推断扣哪一笔
    → 这是沪市的主场景（上交所 L2 通常不提供委托编号）

模式 B：只有成交 + 快照，没有委托流
    → 只能「快照锚定 + 成交推断」，误差必然累积（见 SSEApproxRebooker）

两种模式的差别，用一句话说：
    A 看得见挂单，只是不知道每笔成交对应哪一笔 → 可以精确推断
    B 连挂单都看不见 → 只能估，误差是天花板
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from book import OrderBook  # noqa: E402

# 沪市成交方向标记 → 主动方
BS_MAP = {"B": "B", "S": "S", "N": "N", " ": "N", "": "N"}


class SSERebooker:
    """模式 A：有委托流、成交无委托号。

    核心思路：**既然成交不告诉你对手是谁，那就自己撮合。**

        有委托流 → 每一笔挂单你都看得见 → 按价格-时间优先自己撮合，
                   就能得到和交易所一样的簿。成交记录只用来核对。

    集合竞价单独处理：9:15–9:25 只累积不撮合，等第一条 9:25 成交出现时，
    用它的价格作为竞价成交价，一次性撮合。
    """

    AUC_END = 92500000

    def __init__(self):
        self.book = OrderBook()
        self.miss = {"order": 0, "trade": 0}
        self.stats = {"added": 0.0, "traded": 0.0, "cancelled": 0.0}
        self.buffer = []          # 竞价期间累积的委托
        self.auction_done = False
        self.records = []

    # ------------------------------------------------------------------
    def on_order(self, m):
        """处理一笔委托：竞价期间只缓冲，连续竞价期间直接撮合。"""
        seq = int(m["ApplSeqNum"])
        t = int(m["TransactTime"])
        side = "B" if str(m["Side"]) in ("1", "B", "b") else "S"
        otype = str(m["OrdType"])
        price = round(float(m["Price"]), 2)
        qty = float(m["OrderQty"])

        if not self.auction_done and t < self.AUC_END:
            self.buffer.append({"seq": seq, "side": side, "type": otype,
                                "price": price, "qty": qty, "t": t})
            return

        if otype == "1":                       # 市价单：立即吃对手方
            self._match(seq, side, None, qty)
            return
        if otype == "3":                       # 本方最优
            best = self.book.best(side, 1)
            if not best:
                self.miss["order"] += 1
                return
            price = best[0][0]
        left = self._match(seq, side, price, qty)
        if left > 0:
            self.book.add(seq, side, price, left)
            self.stats["added"] += left

    # ------------------------------------------------------------------
    def _match(self, seq, side, limit, qty):
        """主动方在簿里吃对手方，返回没吃掉的量。"""
        opp = "S" if side == "B" else "B"
        left = qty
        while left > 1e-9:
            top = self.book.best(opp, 1)
            if not top:
                break
            p = top[0][0]
            if limit is not None:
                if side == "B" and p > limit:
                    break
                if side == "S" and p < limit:
                    break
            dq = self.book.queues[opp][p]
            oseq = dq[0]
            take = min(left, self.book.orders[oseq]["qty"])
            self.book.reduce(oseq, take)
            self.stats["traded"] += take
            left -= take
        return left

    # ------------------------------------------------------------------
    def on_trade(self, price, qty, aggressor):
        """成交记录：A 模式下我们已经自己撮合了，这里只用来触发竞价撮合。"""
        return

    def on_cancel(self, seq, qty):
        """撤单：可能撤的是簿里的，也可能撤的是「竞价缓冲里还没撮合的」。"""
        seq = int(seq)
        # 先看竞价缓冲（9:15–9:20 可以撤单，此时委托还没进簿）
        for o in self.buffer:
            if o["seq"] == seq:
                take = min(float(qty), o["qty"])
                o["qty"] -= take
                self.stats["cancelled"] += take
                return
        got = self.book.reduce(seq, float(qty))
        self.stats["cancelled"] += got

    # ------------------------------------------------------------------
    def _run_auction(self, price):
        """9:25 一次性撮合：买单出价 ≥ p、卖单出价 ≤ p，按价格-时间优先。"""
        price = round(float(price), 2)
        bids = sorted([o for o in self.buffer if o["side"] == "B" and o["price"] >= price],
                      key=lambda o: (-o["price"], o["seq"]))
        asks = sorted([o for o in self.buffer if o["side"] == "S" and o["price"] <= price],
                      key=lambda o: (o["price"], o["seq"]))
        i = j = 0
        while i < len(bids) and j < len(asks):
            take = min(bids[i]["qty"], asks[j]["qty"])
            if take > 0:
                self.stats["traded"] += take * 2
            bids[i]["qty"] -= take
            asks[j]["qty"] -= take
            if bids[i]["qty"] <= 1e-9:
                i += 1
            if asks[j]["qty"] <= 1e-9:
                j += 1
        # 未成交的进入连续竞价
        for o in self.buffer:
            if o["qty"] > 0 and o["type"] != "1":
                self.book.add(o["seq"], o["side"], o["price"], o["qty"])
                self.stats["added"] += o["qty"]
        self.auction_done = True
        self.buffer = []

    # ------------------------------------------------------------------
    def run(self, orders: pd.DataFrame, trades: pd.DataFrame,
            snap_times=None, snap_seqs=None):
        """合并两路消息并回放。"""
        ev = pd.concat([orders.assign(evt="O"), trades.assign(evt="T")], ignore_index=True)
        ev = ev.sort_values(["ChannelNo", "ApplSeqNum"], kind="stable")

        times = sorted(snap_times or [])
        seqs = sorted(snap_seqs or [])
        pj = pi = 0

        for row in ev.itertuples(index=False):
            t, seq = int(row.TransactTime), int(row.ApplSeqNum)
            while pj < len(times) and t > times[pj]:
                self._record(times[pj])
                pj += 1

            d = row._asdict()
            if row.evt == "O":
                self.on_order(d)
            elif str(d.get("ExecType", "4")) == "F":
                sid = int(d.get("BidApplSeqNum") or 0) or int(d.get("AskApplSeqNum") or 0)
                self.on_cancel(sid, d["TradeQty"])
            else:
                if not self.auction_done and t >= self.AUC_END:
                    self._run_auction(d["Price"])

            while pi < len(seqs) and seq >= seqs[pi]:
                self._record(seqs[pi])
                pi += 1

        while pj < len(times):
            self._record(times[pj])
            pj += 1
        while pi < len(seqs):
            self._record(seqs[pi])
            pi += 1
        return self

    def _record(self, key):
        self.records.append((key, self.book.snapshot(10)))


class SSEApproxRebooker:
    """模式 B：只有成交 + 快照时的近似重建。

    数据长这样（没有委托号）：
        时间, 成交价格, 成交数量, BS标志
        93000000, 11.48, 300, B

    流程：
        1. seed()     用 9:30 的十档快照打底
        2. on_trade() 每来一笔成交，从对手方扣减
        3. snapshot() 输出当前十档，供 test_sse.py 比对
    """

    def __init__(self):
        self.bid = {}      # price -> qty
        self.ask = {}
        self.miss = 0      # 扣不到的笔数（成交价不在已知档位里）

    def seed(self, snap):
        """【你来写】为什么沪市要用快照打底，而不能像深市那样从空簿开始？"""
        self.bid = {round(float(p), 2): float(q) for p, q in snap["bid"] if q > 0}
        self.ask = {round(float(p), 2): float(q) for p, q in snap["ask"] if q > 0}

    def on_trade(self, price, qty, aggressor):
        """【你来写】为什么扣不到时要记 miss，而不是扣到最接近的档位上？"""
        price = round(float(price), 2)
        book = self.ask if str(aggressor).upper() == "B" else self.bid
        if price not in book:
            self.miss += 1          # 10 档之外，看不见，只能记一笔
            return
        book[price] -= qty
        if book[price] <= 1e-9:
            del book[price]

    def snapshot(self, n=10):
        """【你来写】为什么输出时买侧要降序、卖侧要升序？"""
        bids = sorted(self.bid.items(), key=lambda x: -x[0])[:n]
        asks = sorted(self.ask.items(), key=lambda x: x[0])[:n]
        return {"bid": bids, "ask": asks}
