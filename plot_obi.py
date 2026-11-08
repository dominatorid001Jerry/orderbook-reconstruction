# -*- coding: utf-8 -*-
"""OBI 的两张图：

    图 1  obi_hist.png   分布直方图（bin plot）——看它落在什么范围、有没有偏
    图 2  obi_bins.png   分箱收益图——看 OBI 越大，未来收益是不是越高

用法：python plot_obi.py
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
    p = build_panel(sims, make_grid(30)).dropna(subset=["obi", "mid"])
    p = p.sort_values(["code", "time"])
    p["ret"] = p.groupby("code")["mid"].shift(-1) / p["mid"] - 1
    return p.dropna(subset=["ret"])


def plot_hist(panel):
    plt.figure(figsize=(8, 4.5))
    bins = np.linspace(-1, 1, 51)
    for code, g in panel.groupby("code"):
        plt.hist(g["obi"], bins=bins, alpha=0.55, label=f"{code} {CODES[code]}")
    plt.axvline(0, color="black", lw=1)
    plt.axvline(panel["obi"].mean(), color="red", ls="--", lw=1.2,
                label=f"mean={panel['obi'].mean():+.2f}")
    for x in (-0.5, 0.5):
        plt.axvline(x, color="gray", ls=":", lw=1)
    plt.xlabel("OBI (5-level, equal weight)")
    plt.ylabel("count")
    plt.title("OBI distribution — 2026-01-13, 30s sampling")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT / "obi_hist.png", dpi=140)
    plt.close()


def plot_bins(panel, q=10):
    """把 OBI 分成 10 箱，画每箱的平均未来收益。这才是判断因子有没有用的图。"""
    plt.figure(figsize=(8, 4.5))
    for code, g in panel.groupby("code"):
        g = g.copy()
        g["bin"] = pd.qcut(g["obi"], q, labels=False, duplicates="drop")
        m = g.groupby("bin").agg(obi=("obi", "mean"), ret=("ret", "mean"), n=("ret", "size"))
        plt.plot(m["obi"], m["ret"] * 1e4, marker="o", label=f"{code} {CODES[code]}")
    plt.axhline(0, color="gray", lw=0.8)
    plt.xlabel("OBI (bin mean)")
    plt.ylabel("mean forward return (bp, 30s)")
    plt.title("OBI bins vs next-30s return")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT / "obi_bins.png", dpi=140)
    plt.close()
    return panel


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    print(f"样本 {len(panel):,} 行")

    plot_hist(panel)
    plot_bins(panel)

    print(f"  均值 {panel['obi'].mean():+.3f}  标准差 {panel['obi'].std():.3f}")
    for code, g in panel.groupby("code"):
        v = g["obi"]
        print(f"  {code}: 中位数 {v.median():+.3f}  |OBI|>0.5 占 {(v.abs()>0.5).mean():.1%}"
              f"  |OBI|>0.8 占 {(v.abs()>0.8).mean():.1%}")
    print(f"图已保存：{OUT}")


if __name__ == "__main__":
    main()
