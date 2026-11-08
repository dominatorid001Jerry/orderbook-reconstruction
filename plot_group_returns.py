# -*- coding: utf-8 -*-
"""分组收益图（bin plot）：把 OBI 从小到大分 10 组，画每组的平均未来收益。

这正是老师要的图：
    横轴 = OBI 分组（第 1 组最低，第 10 组最高）
    纵轴 = 该组未来 N 秒的平均收益（bp）
    看的是：柱子是不是从左到右一路走高（单调性）

用法：python plot_group_returns.py
输出：data/figs/group_returns.png
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

from factor import build_panel, make_grid  # noqa: E402
from wind import load_folder  # noqa: E402

CODES = {"000001": "PingAn", "000002": "Vanke"}
OUT = HERE / "data" / "figs"


def load_panel(date="20260113"):
    sims = {}
    for code in CODES:
        d = load_folder(HERE / "data" / date / f"{code}.SZ")
        sims[code] = {"orders": d["orders"], "trades": d["trades"]}
    return build_panel(sims, make_grid(30)).dropna(subset=["obi", "mid"])


def group_table(sub, h=1, groups=10):
    """按 OBI 分位数组，返回每组的 OBI 均值与未来收益均值。"""
    sub = sub.sort_values("time").reset_index(drop=True)
    mid = sub["mid"].to_numpy()
    fwd = np.append(mid[h:] / mid[:-h] - 1.0, [np.nan] * h)
    d = pd.DataFrame({"obi": sub["obi"].to_numpy(), "ret": fwd}).dropna()
    # 用 rank 再 qcut：OBI 有大量重复值（同价位同量），直接 qcut 会丢箱
    d["g"] = pd.qcut(d["obi"].rank(method="first"), groups, labels=False)
    return d.groupby("g").agg(obi=("obi", "mean"), ret=("ret", "mean"), n=("ret", "size"))


def main(h=1, groups=10):
    OUT.mkdir(parents=True, exist_ok=True)
    panel = load_panel()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    summary = []
    for ax, (code, sub) in zip(axes, panel.groupby("code")):
        m = group_table(sub, h=h, groups=groups)
        x = np.arange(len(m))
        bars = ax.bar(x, m["ret"] * 1e4, color="steelblue", alpha=0.85)
        ax.axhline(0, color="black", lw=0.8)
        # 给每根柱子标数值
        for xi, v in zip(x, m["ret"] * 1e4):
            ax.annotate(f"{v:+.1f}", (xi, v),
                        textcoords="offset points", xytext=(0, 4 if v >= 0 else -11),
                        ha="center", fontsize=7)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{i+1}" for i in x], fontsize=8)
        ax.set_title(f"{code} {CODES[code]}")
        ax.set_xlabel("OBI group (1 = lowest, %d = highest)" % len(m))

        ls = m["ret"].iloc[-1] - m["ret"].iloc[0]
        rho = m["ret"].rank().corr(pd.Series(x).rank())
        summary.append({"code": code, "lo": m["ret"].iloc[0] * 1e4,
                        "hi": m["ret"].iloc[-1] * 1e4,
                        "long_short": ls * 1e4, "rank_corr": rho,
                        "monotonic": bool(m["ret"].is_monotonic_increasing)})

    axes[0].set_ylabel(f"mean forward return (bp, {h*30}s)")
    fig.suptitle(f"OBI grouped returns - h={h} ({h*30}s), 10 groups", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "group_returns.png", dpi=140)
    plt.close()

    print(f"持有期 h={h}（{h*30} 秒），分 {groups} 组\n")
    print(f"{'股票':10s}{'最低组':>9s}{'最高组':>9s}{'多空':>9s}{'秩相关':>8s}  单调")
    for r in summary:
        print(f"{r['code']:10s}{r['lo']:+9.2f}{r['hi']:+9.2f}{r['long_short']:+9.2f}"
              f"{r['rank_corr']:+8.2f}  {r['monotonic']}")
    print(f"\n图已保存：{OUT / 'group_returns.png'}")


if __name__ == "__main__":
    main()
