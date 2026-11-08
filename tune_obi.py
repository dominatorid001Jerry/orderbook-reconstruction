# -*- coding: utf-8 -*-
"""OBI 参数敏感性：档位数 n × 持有期 h 的 IC 矩阵，并画调参图 + 最终 binplot。

用法：python tune_obi.py
输出：
    data/figs/tune_ic_by_level.png    IC 随档位数的变化（多条持有期）
    data/figs/final_binplot.png       最终分组收益图
    data/figs/tune_matrix.csv         完整矩阵
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from factor import obi5  # noqa: E402
from replay_szse import SZRebooker  # noqa: E402
from wind import load_folder  # noqa: E402

CODES = {"000001": "PingAn", "000002": "Vanke"}
OUT = HERE / "data" / "figs"
LEVELS = [1, 3, 5, 10]
HORIZONS = [1, 3, 5, 10]


def series_for(code, date="20260113"):
    d = load_folder(HERE / "data" / date / f"{code}.SZ")
    s = d["snaps"]
    s = s[s["TransactTime"] >= 93000000].reset_index(drop=True)
    rb = SZRebooker().run(d["orders"], d["trades"], snap_times=s["TransactTime"].tolist())
    bid = [[q for _, q in snap["bid"]][:10] for _, snap in rb.records]
    ask = [[q for _, q in snap["ask"]][:10] for _, snap in rb.records]
    mid = np.array([snap["mid"] if snap["mid"] else np.nan for _, snap in rb.records])
    return bid, ask, mid


def ic_for(bid, ask, mid, n, h):
    obi = np.array([obi5(b, a, n) for b, a in zip(bid, ask)], dtype=float)
    fwd = np.append(mid[h:] / mid[:-h] - 1.0, [np.nan] * h)
    ok = np.isfinite(obi) & np.isfinite(fwd)
    x, y = obi[ok], fwd[ok]
    if len(x) < 100 or x.std() == 0 or y.std() == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), x.mean()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    cache = {}
    for code in CODES:
        bid, ask, mid = series_for(code)
        cache[code] = (bid, ask, mid)
        for n in LEVELS:
            for h in HORIZONS:
                ic, mean_obi = ic_for(bid, ask, mid, n, h)
                rows.append({"code": code, "n": n, "h": h, "ic": ic, "mean_obi": mean_obi})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "tune_matrix.csv", index=False, encoding="utf-8-sig")

    print("=== IC 矩阵（行=n 档位数，列=h 持有期）===")
    for code, g in df.groupby("code"):
        print(f"\n{code} {CODES[code]}")
        print(g.pivot(index="n", columns="h", values="ic").round(4).to_string())

    print("\n=== 每个档位数下 OBI 的均值（看正偏有没有变小）===")
    print(df[df.h == 1].pivot(index="n", columns="code", values="mean_obi").round(3).to_string())

    # ---- 图 1：IC vs 档位数 ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, (code, g) in zip(axes, df.groupby("code")):
        for h in HORIZONS:
            sub = g[g.h == h].sort_values("n")
            ax.plot(sub["n"], sub["ic"], marker="o", label=f"h={h} ({h*30}s)")
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_xticks(LEVELS)
        ax.set_xlabel("levels (n)")
        ax.set_title(f"{code} {CODES[code]}")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("IC")
    fig.suptitle("IC vs number of levels", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "tune_ic_by_level.png", dpi=140)
    plt.close()

    # ---- 图 2：最终 binplot（n=5, h=1）----
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, (code, (bid, ask, mid)) in zip(axes, cache.items()):
        obi = np.array([obi5(b, a, 10) for b, a in zip(bid, ask)], dtype=float)
        fwd = np.append(mid[1:] / mid[:-1] - 1.0, np.nan)
        d = pd.DataFrame({"obi": obi, "ret": fwd}).dropna()
        d["g"] = pd.qcut(d["obi"].rank(method="first"), 10, labels=False)
        m = d.groupby("g")["ret"].mean() * 1e4
        x = np.arange(len(m))
        ax.bar(x, m.values, color="steelblue", alpha=0.85)
        ax.axhline(0, color="black", lw=0.8)
        for xi, v in zip(x, m.values):
            ax.annotate(f"{v:+.1f}", (xi, v), textcoords="offset points",
                        xytext=(0, 4 if v >= 0 else -11), ha="center", fontsize=7)
        ls = m.iloc[-1] - m.iloc[0]
        ax.set_title(f"{code} {CODES[code]}   long-short={ls:+.2f}bp")
        ax.set_xticks(x)
        ax.set_xticklabels(range(1, len(m) + 1), fontsize=8)
        ax.set_xlabel("OBI group (1=lowest, 10=highest)")
    axes[0].set_ylabel("mean forward return (bp, 30s)")
    fig.suptitle("Final binplot: OBI n=10, h=1, 10 groups", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "final_binplot.png", dpi=140)
    plt.close()

    print(f"\n图已保存：{OUT}")


if __name__ == "__main__":
    main()

