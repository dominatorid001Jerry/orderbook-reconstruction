# -*- coding: utf-8 -*-
"""五档等权 orderbook imbalance（OBI）因子，以及 IC / RankIC 的计算。

因子定义（等权 = 不按距离加权，五档求和直接相减再除以总和）：

    OBI_5 = (Σ买一~买五 的量 − Σ卖一~卖五 的量) / (Σ买一~买五 的量 + Σ卖一~卖五 的量)

取值范围 [-1, 1]，正值表示买盘厚。
"""
import numpy as np
import pandas as pd

from replay_szse import SZRebooker


# --------------------------------------------------------------------------
# 因子
# --------------------------------------------------------------------------
def obi5(bid_qty, ask_qty, levels=5):
    """五档等权 OBI 因子。

    买盘厚度问的不是「谁的量多」，而是「买盘比卖盘厚多少倍」。
    绝对数量会被两个东西污染：股票股数不同、股价高低不同。

    所以要把量除以总深度，把股数变成一个比例，
    结果落在 [-1, 1]，这样不同股票、不同时间才可比。

    正值表示买盘厚；负值表示卖盘厚。
    """
    b = float(sum(bid_qty[:levels]))
    a = float(sum(ask_qty[:levels]))
    if b + a <= 0:
        return np.nan
    return (b - a) / (b + a)


# --------------------------------------------------------------------------
# 用重建出来的簿，在一张统一的时间网格上采样
# --------------------------------------------------------------------------
def make_grid(step_sec=30):
    """生成统一采样时间网格：上午 9:30-11:30，下午 13:00-14:57。"""
    def ts(h, m, s):
        return h * 10_000_000 + m * 100_000 + s * 1_000

    out = []
    t = ts(9, 30, 0)
    while t <= ts(11, 30, 0):
        out.append(t)
        t += step_sec * 1000
    t = ts(13, 0, 0)
    while t <= ts(14, 57, 0):
        out.append(t)
        t += step_sec * 1000
    return out


def build_panel(sims, grid, levels=5):
    """sims: {code: {'orders': df, 'trades': df}}

    返回长表：code / time / obi / mid
    """
    rows = []
    for code, r in sims.items():
        rb = SZRebooker()
        rb.run(r["orders"], r["trades"], snap_times=grid)
        for t, snap in rb.records:
            bid_qty = [q for _, q in snap["bid"]][:levels]
            ask_qty = [q for _, q in snap["ask"]][:levels]
            rows.append({
                "code": code, "time": t,
                "obi": obi5(bid_qty, ask_qty, levels),
                "mid": snap["mid"],
            })
    return pd.DataFrame(rows)


def add_forward_return(panel, horizon=1):
    panel = panel.sort_values(["code", "time"]).copy()
    panel["ret"] = panel.groupby("code")["mid"].shift(-horizon) / panel["mid"] - 1.0
    return panel


# --------------------------------------------------------------------------
# IC / RankIC
# --------------------------------------------------------------------------
def ic_series(panel, min_stocks=10):
    """按时间截面算 IC（Pearson）和 RankIC（Spearman）。

    每只股票的收益 = 大盘成分 + 个股成分。
    如果把所有股票、所有时间「拉平」算一个相关系数，
    就会把大盘影响这个共同成分混进来，得到虚高的假结果。

    所以必须按时间分组：同一时刻，只比不同股票之间的相对强弱，
    这样大盘的共同涨跌被抵消，剩下的才是「因子选股能力」。
    """
    out = []
    for t, sub in panel.dropna(subset=["obi", "ret"]).groupby("time", sort=True):
        if len(sub) < min_stocks:
            continue
        x, y = sub["obi"], sub["ret"]
        if x.std() == 0 or y.std() == 0:
            continue
        ic = float(np.corrcoef(x, y)[0, 1])
        ric = float(np.corrcoef(x.rank(), y.rank())[0, 1])
        out.append({"time": t, "ic": ic, "rank_ic": ric, "n": len(sub)})
    return pd.DataFrame(out)


def summarize(ic_df, label=""):
    if ic_df.empty:
        print("无有效截面")
        return {}
    ic, ric = ic_df["ic"], ic_df["rank_ic"]
    res = {
        "label": label,
        "sections": len(ic_df),
        "ic_mean": ic.mean(), "ic_std": ic.std(),
        "ir": ic.mean() / ic.std() if ic.std() else np.nan,
        "t": ic.mean() / ic.std() * np.sqrt(len(ic)) if ic.std() else np.nan,
        "ic_pos_rate": (ic > 0).mean(),
        "rank_ic_mean": ric.mean(),
        "rank_ic_ir": ric.mean() / ric.std() if ric.std() else np.nan,
    }
    print(f"  [{label}] 截面数={res['sections']}  "
          f"IC均值={res['ic_mean']:+.4f}  IC标准差={res['ic_std']:.4f}  "
          f"IR={res['ir']:+.4f}  t={res['t']:+.2f}  正IC占比={res['ic_pos_rate']:.1%}")
    print(f"       RankIC均值={res['rank_ic_mean']:+.4f}  RankIC_IR={res['rank_ic_ir']:+.4f}")
    return res


# --------------------------------------------------------------------------
# 只有一两只股票时：时序 IC（不是截面 IC）
# --------------------------------------------------------------------------
def ts_ic(panel, min_obs=60):
    """对每只股票单独算：因子序列 和 未来收益序列 的相关。

    这是「时序 IC」，和「截面 IC」是两个完全不同的东西：
    - 截面 IC：同一时刻，不同股票之间的排序能力；
    - 时序 IC：同一只股票，不同时刻之间的排序能力。
    股票数量太少时，只能算时序 IC。
    """
    rows = []
    for code, sub in panel.groupby("code"):
        sub = sub.sort_values("time")
        x, y = sub["obi"], sub["ret"]
        ok = x.notna() & y.notna()
        x, y = x[ok], y[ok]
        if len(x) < min_obs or x.std() == 0 or y.std() == 0:
            continue
        rows.append({
            "code": code, "n": len(x),
            "ic": float(np.corrcoef(x, y)[0, 1]),
            "rank_ic": float(np.corrcoef(x.rank(), y.rank())[0, 1]),
        })
    return pd.DataFrame(rows)


def rolling_rank_ic(panel, code=None, window=120):
    """滚动 RankIC：看因子有效性能不能「持续」，而不是某一段特别灵。

    做法：在每个窗口内先各自排名，再算相关（这就是窗口内的 Spearman）。
    """
    sub = panel if code is None else panel[panel["code"] == code]
    sub = sub.sort_values("time").dropna(subset=["obi", "ret"]).reset_index(drop=True)
    if len(sub) < window + 1:
        return pd.Series(dtype=float)

    obi = sub["obi"].to_numpy()
    ret = sub["ret"].to_numpy()
    idx = sub["time"].to_numpy()
    vals = []
    for i in range(window, len(sub) + 1):
        x, y = obi[i - window:i], ret[i - window:i]
        if x.std() == 0 or y.std() == 0:
            vals.append(np.nan)
            continue
        rx = pd.Series(x).rank().to_numpy()
        ry = pd.Series(y).rank().to_numpy()
        vals.append(float(np.corrcoef(rx, ry)[0, 1]))
    return pd.Series(vals, index=idx[window - 1:])
