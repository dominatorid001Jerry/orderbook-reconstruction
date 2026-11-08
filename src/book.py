# -*- coding: utf-8 -*-
"""订单簿核心数据结构。

设计要点（看代码前先读这三行）：
1. 订单簿 = 价格 → 队列。每个价位是一个 FIFO 队列，队列里存的是「委托编号」。
2. 价格本身是有序的：买侧从高到低、卖侧从低到高，取最优价就是取极值。
3. 所以一个订单簿只需要两个索引：seq → 委托明细，价格 → 委托编号队列。
"""
from collections import defaultdict, deque


class OrderBook:
    """限价订单簿（L3 级别：每一笔委托都能追踪）。"""

    def __init__(self):
        # seq -> {"side": "B"/"S", "price": float, "qty": float}
        self.orders = {}
        # side -> price -> deque[seq]，队首是时间最早的那笔（价格-时间优先）
        self.queues = {"B": defaultdict(deque), "S": defaultdict(deque)}
        # side -> price -> 该价位的总剩余量（缓存，避免每次求和）
        self.totals = {"B": defaultdict(float), "S": defaultdict(float)}

    # ---------------- 增删改 ----------------

    def add(self, seq, side, price, qty):
        """一笔新委托进来，要同时更新三个地方：

        ① orders[seq]：记下编号、买还是卖、价格、多少股
           不做的话，成交时没有编号就找不到那笔委托。

        ② queues[side][price]：把编号追加到队尾
           不做的话，同价位的时序性会被打乱。

        ③ totals[side][price]：把这个价位的总股数加上这笔的数量
           不做的话，盘口显示的是旧数（甚至这一档不显示）。

        注意：这个方法不撮合、不核对，那是交易所和 validate.py 的活。
        """
        if qty <= 0:
            return
        self.orders[seq] = {"side": side, "price": price, "qty": float(qty)}
        self.queues[side][price].append(seq)   # 排到队尾 = 时间优先
        self.totals[side][price] += qty

    def reduce(self, seq, qty):
        """成交或部分撤单：把某笔委托的剩余量减掉 qty，减到 0 就整条删除。"""
        o = self.orders.get(seq)
        if not o:
            return 0.0
        q = min(qty, o["qty"])
        o["qty"] -= q
        self.totals[o["side"]][o["price"]] -= q
        if o["qty"] <= 1e-9:
            self._remove(seq)
        return q

    def _remove(self, seq):
        """删除一笔委托时，三个结构都要动，少一个都会出问题。

        ① orders：删掉这条委托的整条明细。
        ② queues：从这个价位的队列里摘掉这个编号。
        ③ totals：这个价位的总量减掉它的剩余量。

        少维护一个的后果：
        - 不删 orders → 字典里永远留着它 → 内存越跑越大；将来编号复用或查错时会读到幽灵委托。
        - 不删 queues → 队列里躺着一个已经死掉的编号 → 下次成交扣到它，reduce 找不到 → 扣减失败。
        - 不删 totals → 这个价位的总量虚高 → 盘口显示的量比真实多。

        还有一个细节：如果这个价位被删空了，还要把价位从 queues 和 totals 里都删掉，
        否则 best() 会读到「量 = 0 的假档位」，五档就错位了。
        """
        o = self.orders.pop(seq, None)
        if not o:
            return
        dq = self.queues[o["side"]][o["price"]]
        try:
            dq.remove(seq)
        except ValueError:
            pass
        if not dq:                                   # 该价位空了，把价位也删掉
            del self.queues[o["side"]][o["price"]]
            del self.totals[o["side"]][o["price"]]

    # ---------------- 查询 ----------------

    def best(self, side, n=5):
        """返回前 n 档 (price, qty)，买侧降序、卖侧升序。

        因为买一价是买侧最高的价，卖一价是卖侧最低的价，
        所以两边都要让「最优价」排在第一位。

        如果两边都按升序排，买侧的第一个就会变成最低买价，
        买一直接变成最低价，最优价反而被挤到了最后。
        """
        prices = sorted(self.totals[side].keys(), reverse=(side == "B"))
        out = []
        for p in prices[:n]:
            q = self.totals[side][p]
            if q > 1e-9:
                out.append((p, q))
        return out

    def mid(self):
        """中间价；单边为空时返回 None（涨跌停时会发生）。"""
        b = self.best("B", 1)
        a = self.best("S", 1)
        if not b or not a:
            return None
        return (b[0][0] + a[0][0]) / 2.0

    def depth(self, side, n=5):
        return sum(q for _, q in self.best(side, n))

    def snapshot(self, n=5):
        """输出某个时刻的 n 档盘口，用于和官方快照比对。"""
        return {
            "bid": self.best("B", n),
            "ask": self.best("S", n),
            "mid": self.mid(),
        }

    def __len__(self):
        return len(self.orders)
