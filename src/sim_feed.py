# -*- coding: utf-8 -*-
"""逐笔行情的模拟器（没有真实 Level-2 数据时，用它把整条链路跑通）。

⚠️ 重要：这是**合成数据**，不是真实行情。它的唯一用途是让你在没有
券商 L2 权限时，也能验证「重建代码」和「因子代码」是否正确。
接上真实数据后，这个文件整体替换掉，其余代码不用改。

它按深交所的字段结构产出三张表：
    orders  逐笔委托：ChannelNo / ApplSeqNum / TransactTime / Price / OrderQty / Side / OrdType
    trades  逐笔成交：ChannelNo / ApplSeqNum / TransactTime / Price / TradeQty / ExecType
                      / BidApplSeqNum / AskApplSeqNum
    snaps   十档快照：时间 / 买十档 / 卖十档 / 最新价
"""
import random
from collections import defaultdict

from book import OrderBook

TICK = 0.01


# --------------------------------------------------------------------------
# 时间工具
# --------------------------------------------------------------------------
def _ts(h, m, s, ms=0):
    return h * 10_000_000 + m * 100_000 + s * 1_000 + ms


OPEN_AUC = (_ts(9, 15, 0), _ts(9, 25, 0))        # 开盘集合竞价
AM = (_ts(9, 30, 0), _ts(11, 30, 0))             # 上午连续竞价
PM = (_ts(13, 0, 0), _ts(14, 57, 0))             # 下午连续竞价（14:57 之后是收盘集合竞价）
CLOSE_AUC = (_ts(14, 57, 0), _ts(15, 0, 0))      # 收盘集合竞价


def _rand_time(rng, span, lo, hi):
    return rng.randint(lo, hi) if False else rng.randrange(lo, hi)


# --------------------------------------------------------------------------
# 撮合引擎：只在「模拟交易所」里用；重建订单簿时不需要它
# --------------------------------------------------------------------------
class Exchange:
    def __init__(self, code, prev_close):
        self.code = code
        self.prev_close = prev_close
        self.book = OrderBook()
        self.seq = 0
        self.orders = []
        self.trades = []
        self.last = prev_close

    def _next(self):
        self.seq += 1
        return self.seq

    def _emit_trade(self, t, price, qty, bid_seq, ask_seq, aggressor="B"):
        self.seq += 1
        self.trades.append({
            "ChannelNo": 1, "ApplSeqNum": self.seq, "SecurityID": self.code,
            "TransactTime": t, "Price": round(price, 2), "TradeQty": int(qty),
            "ExecType": "4", "BidApplSeqNum": bid_seq, "AskApplSeqNum": ask_seq, "Aggressor": aggressor,
        })

    def _emit_cancel(self, t, seq, qty):
        o = self.book.orders.get(seq)
        side_id = seq if o and o["side"] == "B" else 0
        side_id2 = seq if o and o["side"] == "S" else 0
        self.seq += 1
        self.trades.append({
            "ChannelNo": 1, "ApplSeqNum": self.seq, "SecurityID": self.code,
            "TransactTime": t, "Price": o["price"] if o else 0.0, "TradeQty": int(qty),
            "ExecType": "F", "BidApplSeqNum": side_id, "AskApplSeqNum": side_id2,
        })

    # ---- 连续竞价撮合 ----
    def _market_take(self, t, side, qty):
        """市价单为什么要单独处理？它为什么不能进订单簿？

        市价单没有价格（字段是 0），意味着它不需要在簿里排队——来了就按对手方的价格成交。
        如果按 0 元挂进簿里，盘口会多出一个「0 元」的假档位。

        所以它自己那一侧永远不进簿、也不用扣；
        它的成交只能通过成交流里的记录，去扣减对手方那笔委托。
        """
        opp = "S" if side == "B" else "B"
        orders = self.orders
        own_seq = orders[-1]["ApplSeqNum"] if orders else 0
        while qty > 0:
            top = self.book.best(opp, 1)
            if not top:
                break
            p, _ = top[0]
            dq = self.book.queues[opp][p]
            while qty > 0 and dq:
                oseq = dq[0]
                take = min(qty, self.book.orders[oseq]["qty"])
                bid_seq = own_seq if side == "B" else oseq
                ask_seq = own_seq if side == "S" else oseq
                self._emit_trade(t, p, take, bid_seq, ask_seq, aggressor=side)
                self.book.reduce(oseq, take)
                qty -= take
        if qty > 0:                       # 市价单剩余部分撤销
            self._emit_cancel(t, own_seq, qty)

    def _limit_take(self, t, seq, side, price, qty):
        opp = "S" if side == "B" else "B"
        while qty > 0:
            top = self.book.best(opp, 1)
            if not top:
                break
            p = top[0][0]
            if (side == "B" and p > price) or (side == "S" and p < price):
                break
            dq = self.book.queues[opp][p]
            while qty > 0 and dq:
                oseq = dq[0]
                take = min(qty, self.book.orders[oseq]["qty"])
                bid_seq = seq if side == "B" else oseq
                ask_seq = seq if side == "S" else oseq
                self._emit_trade(t, p, take, bid_seq, ask_seq, aggressor=side)
                self.book.reduce(oseq, take)
                qty -= take
        return qty

    def submit(self, t, side, price, qty, ord_type="2"):
        seq = self._next()
        self.orders.append({
            "ChannelNo": 1, "ApplSeqNum": seq, "SecurityID": self.code,
            "TransactTime": t, "Price": 0.0 if ord_type == "1" else round(price, 2),
            "OrderQty": int(qty), "Side": ("1" if side == "B" else "2"), "OrdType": ord_type,
        })
        if ord_type == "1":
            self._market_take(t, side, qty)
            return seq
        rem = self._limit_take(t, seq, side, price, qty)
        if rem > 0:
            self.book.add(seq, side, round(price, 2), rem)
        return seq

    def cancel(self, t, seq_frac=0.3):
        if not self.book.orders:
            return
        seq = random.choice(list(self.book.orders.keys()))
        o = self.book.orders[seq]
        # 撤单量必须是 100 股的整数倍，否则会出现 0.5 股这种真实市场不可能有的余量
        qty = max(100, int(round(o["qty"] * seq_frac / 100.0)) * 100)
        qty = min(qty, o["qty"])
        self._emit_cancel(t, seq, qty)
        self.book.reduce(seq, qty)


# --------------------------------------------------------------------------
# 集合竞价：算出一个能最大化成交量的价格
# --------------------------------------------------------------------------
def call_auction_price(bids, asks, prev_close):
    """集合竞价为什么取「成交量最大」的价格，而不是买卖中间价？

    连续竞价是逐笔撮合，你挂 11.00 只能吃到同价格及比这个价格低的卖单；
    集合竞价是一次性成交，所有人按同一个价一次性成交。

    所以对每个候选价 p，要算：
        愿买的量 = 所有出价大于等于 p 的买单之和
        愿卖的量 = 所有出价小于等于 p 的卖单之和
        成交量 = min(愿买的量, 愿卖的量)

    取成交量最大的那个价当开盘价。

    bids / asks: [(price, qty, seq)]
    """
    if not bids or not asks:
        return None
    prices = sorted({p for p, _, _ in bids} | {p for p, _, _ in asks})
    best_key, best_p = None, None
    for p in prices:
        dem = sum(q for pr, q, _ in bids if pr >= p)   # 愿意在此价及以上买的总量
        sup = sum(q for pr, q, _ in asks if pr <= p)   # 愿意在此价及以下卖的总量
        vol = min(dem, sup)
        key = (vol, -abs(dem - sup), -abs(p - prev_close))
        if best_key is None or key > best_key:
            best_key, best_p = key, p
    return best_p


def run_auction(ex, t, bids, asks):
    """按价格-时间优先撮合，把结果写成逐笔成交。"""
    p = call_auction_price(bids, asks, ex.prev_close)
    if p is None:
        return None, []
    b = sorted([x for x in bids if x[0] >= p], key=lambda x: (-x[0], x[2]))
    a = sorted([x for x in asks if x[0] <= p], key=lambda x: (x[0], x[2]))
    bq = {s: q for _, q, s in b}
    aq = {s: q for _, q, s in a}
    i = j = 0
    filled = []
    while i < len(b) and j < len(a):
        bs, as_ = b[i][2], a[j][2]
        take = min(bq[bs], aq[as_])
        if take <= 0:
            i += 1 if bq[bs] <= 0 else 0
            j += 1 if aq[as_] <= 0 else 0
            continue
        ex._emit_trade(t, p, take, bs, as_, aggressor="N")  # 集合竞价：无主动方
        # 如果这些委托已经在簿里（收盘集合竞价的情况），成交也要从簿里扣掉
        ex.book.reduce(bs, take)
        ex.book.reduce(as_, take)
        bq[bs] -= take
        aq[as_] -= take
        filled.append((bs, as_, take))
        if bq[bs] <= 0:
            i += 1
        if aq[as_] <= 0:
            j += 1
    return p, filled


# --------------------------------------------------------------------------
# 主流程：生成一只股票一整天的数据
# --------------------------------------------------------------------------
def simulate_stock(code, seed, prev_close=10.0, n_auction=250, n_cont=1200,
                   n_close=120, snap_interval_s=3, informed=0.12, cancel_rate=0.25):
    rng = random.Random(seed)
    ex = Exchange(code, prev_close)
    snaps = []
    senti = 0.0          # 情绪（AR(1)），让买卖到达率有持续性

    def price_around(mid, side):
        """挂一个围绕 mid 的价格：多数贴在盘口，少数打穿。"""
        steps = rng.choices([0, 1, 2, 3, 5], weights=[45, 25, 15, 10, 5])[0]
        off = steps * TICK
        if side == "B":
            return round(mid - off, 2) if rng.random() < 0.75 else round(mid + off, 2)
        return round(mid + off, 2) if rng.random() < 0.75 else round(mid - off, 2)

    def clamp(p):
        lo, hi = round(prev_close * 0.9, 2), round(prev_close * 1.1, 2)
        return max(lo, min(hi, round(p, 2)))

    # ---------- 1) 开盘集合竞价 ----------
    bids, asks = [], []
    auc_times = sorted(rng.randrange(*OPEN_AUC) for _ in range(n_auction))
    for i in range(n_auction):
        senti = 0.995 * senti + rng.gauss(0, 0.06)
        side = "B" if rng.random() < 0.5 + informed * senti else "S"
        p = clamp(prev_close * (1 + rng.gauss(0, 0.008)))
        q = rng.choice([100, 200, 300, 500, 800, 1000, 2000])
        seq = ex._next()
        ex.orders.append({"ChannelNo": 1, "ApplSeqNum": seq, "SecurityID": code,
                          "TransactTime": auc_times[i], "Price": p,
                          "OrderQty": q, "Side": ("1" if side == "B" else "2"), "OrdType": "2"})
        (bids if side == "B" else asks).append((p, q, seq))

    t_open = _ts(9, 25, 0)
    op, _ = run_auction(ex, t_open, bids, asks)
    ex.last = op or prev_close
    # 未成交的限价委托进入连续竞价
    filled = defaultdict(int)
    for m in ex.trades:
        filled[m["BidApplSeqNum"]] += m["TradeQty"]
        filled[m["AskApplSeqNum"]] += m["TradeQty"]
    for side, lst in (("B", bids), ("S", asks)):
        for p, q, s in lst:
            rem = q - filled[s]
            if rem > 0:
                ex.book.add(s, side, p, rem)

    def snap(t):
        b = ex.book.best("B", 10)
        a = ex.book.best("S", 10)
        snaps.append({"TransactTime": t, "SecurityID": code, "seq": ex.seq,
                      "bid_px": [x[0] for x in b], "bid_qty": [x[1] for x in b],
                      "ask_px": [x[0] for x in a], "ask_qty": [x[1] for x in a],
                      "last": ex.last})

    snap(t_open)

    # ---------- 2) 连续竞价 ----------
    n_events = n_cont
    n_am = int(n_events * 0.55)
    # 时间必须按先后顺序产生，才能保证 ApplSeqNum 与时间同序（真实行情就是这样）
    cont_times = sorted(rng.randrange(*AM) for _ in range(n_am)) + \
        sorted(rng.randrange(*PM) for _ in range(n_events - n_am))
    for k, t in enumerate(cont_times):
        mid = ex.book.mid() or ex.last
        senti = 0.995 * senti + rng.gauss(0, 0.06)
        side = "B" if rng.random() < 0.5 + informed * senti else "S"
        r = rng.random()
        if r < 0.05:                                   # 5% 市价单
            ex.submit(t, side, 0, rng.choice([100, 200, 500]), ord_type="1")
        else:
            ex.submit(t, side, clamp(price_around(mid, side)),
                      rng.choice([100, 200, 300, 500, 800, 1000, 1500, 2000]))
        if rng.random() < cancel_rate:
            ex.cancel(t, seq_frac=rng.choice([0.3, 0.5, 1.0]))
        # 快照
        if k % max(1, int(snap_interval_s * 3)) == 0:
            snap(t)

    # ---------- 3) 收盘集合竞价 ----------
    bids, asks = [], []
    mid = ex.book.mid() or ex.last
    close_times = sorted(rng.randrange(*CLOSE_AUC) for _ in range(n_close))
    for i in range(n_close):
        side = "B" if rng.random() < 0.5 else "S"
        p = clamp(price_around(mid, side))
        q = rng.choice([100, 200, 500, 1000])
        seq = ex._next()
        ex.orders.append({"ChannelNo": 1, "ApplSeqNum": seq, "SecurityID": code,
                          "TransactTime": close_times[i], "Price": p,
                          "OrderQty": q, "Side": ("1" if side == "B" else "2"), "OrdType": "2"})
        (bids if side == "B" else asks).append((p, q, seq))
        ex.book.add(seq, side, p, q)

    t_close = _ts(15, 0, 0)
    # 收盘竞价参与撮合的只有 14:57 之后进来的委托；这里简化：把新委托单独撮合
    cp, _ = run_auction(ex, t_close, bids, asks)
    if cp:
        ex.last = cp
    snap(t_close)

    ex.orders.sort(key=lambda m: m["ApplSeqNum"])
    ex.trades.sort(key=lambda m: m["ApplSeqNum"])
    return {"orders": ex.orders, "trades": ex.trades, "snaps": snaps, "open_price": op}




