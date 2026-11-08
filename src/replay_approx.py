# -*- coding: utf-8 -*-
"""近似重建：只有「逐笔成交 + 快照」、没有「逐笔委托」时，能做出来的东西。

真实场景：很多人手里只有成交明细（比如腾讯分笔），没有委托流。
那就只能这样重建：

    用快照初始化簿 → 每笔成交从对手方扣减 → 下一张快照来了强制对齐

它一定会错，错在三个地方（这三个地方你必须在报告里写清楚）：
1. 看不见新挂单 —— 两次快照之间新增的委托，你完全不知道；
2. 看不见撤单 —— 撤掉的量还挂在簿里；
3. 只有当成交打在「看得见的价位」时才能扣减。

这个模块的价值不是「能用」，而是**能量化「没有委托流到底损失多少」**。
"""
from collections import defaultdict


class ApproxRebuilder:
    """只有成交和快照时的近似订单簿。"""

    def __init__(self, levels=10):
        self.levels = levels
        self.bids = {}      # price -> qty
        self.asks = {}
        self.miss = 0       # 成交打在不存在的价位上的次数

    # ------------------------------------------------------------------
    def resync(self, snap):
        """用官方快照把簿强制对齐。注意：快照只给前 N 档，更深的档位我们永远不知道。"""
        self.bids = {round(float(p), 2): float(q)
                     for p, q in zip(snap["bid_px"][: self.levels], snap["bid_qty"][: self.levels])}
        self.asks = {round(float(p), 2): float(q)
                     for p, q in zip(snap["ask_px"][: self.levels], snap["ask_qty"][: self.levels])}
        self.bids = {p: q for p, q in self.bids.items() if q > 0}
        self.asks = {p: q for p, q in self.asks.items() if q > 0}

    # ------------------------------------------------------------------
    def apply_trade(self, price, qty, aggressor):
        """按成交扣减对手方。

        aggressor: 'B' 主动买（吃卖盘）/ 'S' 主动卖（吃买盘）/ 'N' 未知（按价格推断）
        """
        price = round(float(price), 2)
        if aggressor == "B":
            side = self.asks
        elif aggressor == "S":
            side = self.bids
        else:
            best_bid = max(self.bids) if self.bids else None
            best_ask = min(self.asks) if self.asks else None
            if best_bid is not None and price <= best_bid:
                side = self.bids
            elif best_ask is not None and price >= best_ask:
                side = self.asks
            else:
                self.miss += 1
                return

        if price not in side:
            self.miss += 1
            return
        side[price] -= qty
        if side[price] <= 1e-9:
            del side[price]

    # ------------------------------------------------------------------
    def best(self, side, n=5):
        book = self.bids if side == "B" else self.asks
        prices = sorted(book.keys(), reverse=(side == "B"))[:n]
        return [(p, book[p]) for p in prices]

    def snapshot(self, n=5):
        return {"bid": self.best("B", n), "ask": self.best("S", n)}
