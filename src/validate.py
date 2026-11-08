# -*- coding: utf-8 -*-
"""校验器：拿重建出来的盘口，和官方快照逐档比对。

这是整个项目里最重要、也最容易被跳过的一步。
重建代码「能跑」不等于「对」——必须用快照把每一档都对上，
否则后面算出来的所有因子都是幻觉。
"""
import numpy as np
import pandas as pd


def _levels(snap, side, n):
    px = snap[f"{side}_px"][:n]
    qty = snap[f"{side}_qty"][:n]
    return [(round(float(p), 2), float(q)) for p, q in zip(px, qty)]


def compare(records, snaps, levels=5, qty_tol=1.0):
    """records: [(打点标识, {'bid':[(p,q)...], 'ask':[...]})]

    snaps:   官方快照 list of dict（字段 bid_px/bid_qty/ask_px/ask_qty）
    返回逐条比对的结果 DataFrame。
    """
    rows = []
    for (key, book), s in zip(records, snaps):
        diffs = 0
        absq = 0.0
        for side in ("bid", "ask"):
            truth = _levels(s, side, levels)
            mine = book[side][:levels]
            for i in range(levels):
                tp, tq = truth[i] if i < len(truth) else (np.nan, 0.0)
                mp, mq = mine[i] if i < len(mine) else (np.nan, 0.0)
                if not (np.isclose(tp, mp, equal_nan=True) and abs(tq - mq) <= qty_tol):
                    diffs += 1
                    absq += abs((tq or 0) - (mq or 0))
        rows.append({"key": key, "diff_levels": diffs, "qty_gap": absq})
    return pd.DataFrame(rows)


def report(df, name=""):
    n = len(df)
    exact = (df["diff_levels"] == 0).sum()
    print(f"  [{name}] 快照数={n}  完全一致={exact} ({exact / max(n, 1):.2%})  "
          f"平均错档={df['diff_levels'].mean():.2f}  最大错档={df['diff_levels'].max()}  "
          f"累计量差={df['qty_gap'].sum():,.0f} 股")
    return {"n": n, "exact_rate": exact / max(n, 1),
            "mean_diff": df["diff_levels"].mean(), "max_diff": df["diff_levels"].max()}
