# -*- coding: utf-8 -*-
"""因子评价：一次算出 OBI 的 9 个体检指标 + 3 张图。

用法：
    python evaluate_factor.py                # 默认 20260113
    python evaluate_factor.py 20260410

输出：
    data/figs/ic_decay.png        IC 随持有期衰减
    data/figs/rolling_ic.png      滚动 IC 稳定性
    data/figs/long_short.png      高/低 OBI 的多空净值
    data/figs/metrics.csv         全部指标
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
HORIZONS = [1, 2, 3, 5, 10, 20]      # 单位：采样点（30 秒/点）
FIG_DIR = HERE / "data" / "figs"


def load_panel(date="20260113", step=30):
    sims = {}
    for code in CODES:
        folder = HERE / "data" / date / f"{code}.SZ"
        d = load_folder(folder)
        sims[code] = {"orders": d["orders"], "trades": d["trades"]}
    panel = build_panel(sims, make_grid(step_sec=step))
    return panel.dropna(subset=["obi", "mid"])


def ic_table(panel, horizons=HORIZONS):
    """对每只股票、每个持有期，算 IC / RankIC / 自相关修正后的 t。"""
    rows = []
    for code, sub in panel.groupby("code"):
        sub = sub.sort_values("time").reset_index(drop=True)
        obi = sub["obi"].to_numpy()
        mid = sub["mid"].to_numpy()
        # 因子自相关（lag-1）
        rho = float(np.corrcoef(obi[:-1], obi[1:])[0, 1]) if len(obi) > 2 else 0.0
        n = len(obi)
        # AR(1) 有效样本量
        n_eff = n * (1 - rho) / (1 + rho) if rho < 1 else n

        for h in horizons:
            if h >= n:
                continue
            f = obi[:-h]
            r = mid[h:] / mid[:-h] - 1.0
            ok = np.isfinite(f) & np.isfinite(r)
            f, r = f[ok], r[ok]
            if len(f) < 50 or f.std() == 0 or r.std() == 0:
                continue
            ic = float(np.corrcoef(f, r)[0, 1])
            ric = float(np.corrcoef(pd.Series(f).rank(), pd.Series(r).rank())[0, 1])
            t_naive = ic * np.sqrt(max(len(f) - 2, 1)) / np.sqrt(max(1 - ic ** 2, 1e-9))
            t_adj = ic * np.sqrt(max(n_eff - 2, 1)) / np.sqrt(max(1 - ic ** 2, 1e-9))
            rows.append({"code": code, "h": h, "seconds": h * 30, "n": len(f),
                         "ic": ic, "rank_ic": ric,
                         "t_naive": t_naive, "t_adj": t_adj,
                         "autocorr": rho, "n_eff": n_eff})
    return pd.DataFrame(rows)


def rolling_ic(panel, window=120):
    out = {}
    for code, sub in panel.groupby("code"):
        sub = sub.sort_values("time").reset_index(drop=True)
        obi = sub["obi"].to_numpy()
        mid = sub["mid"].to_numpy()
        r = np.append(mid[1:] / mid[:-1] - 1.0, np.nan)
        vals = []
        for i in range(window, len(obi)):
            x = obi[i - window:i]
            y = r[i - window:i]
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 30 or x[ok].std() == 0 or y[ok].std() == 0:
                vals.append(np.nan)
            else:
                vals.append(np.corrcoef(x[ok], y[ok])[0, 1])
        out[code] = pd.Series(vals, index=sub["time"].to_numpy()[window:])
    return out


def long_short(panel, q=0.3):
    """时序分组：OBI 在自己历史里的高位 vs 低位，看未来收益差。"""
    rows = []
    curves = {}
    for code, sub in panel.groupby("code"):
        sub = sub.sort_values("time").reset_index(drop=True)
        obi = sub["obi"]
        mid = sub["mid"]
        r = (mid.shift(-1) / mid - 1.0)
        hi, lo = obi.quantile(1 - q), obi.quantile(q)
        rows.append({"code": code,
                     "high_ret": r[obi >= hi].mean(),
                     "low_ret": r[obi <= lo].mean(),
                     "spread": r[obi >= hi].mean() - r[obi <= lo].mean(),
                     "n_high": int((obi >= hi).sum()),
                     "n_low": int((obi <= lo).sum())})
        # 净值：高位持有、低位空仓（简化版多空）
        pos = np.where(obi >= hi, 1.0, np.where(obi <= lo, -1.0, 0.0))
        pnl = pd.Series(pos, index=sub.index) * r.fillna(0)
        curves[code] = (1 + pnl).cumprod()
    return pd.DataFrame(rows), curves


def half_life(ic_df, code):
    sub = ic_df[ic_df["code"] == code].sort_values("h")
    if sub.empty:
        return np.nan
    base = sub.iloc[0]["ic"]
    if base <= 0:
        return np.nan
    for _, row in sub.iterrows():
        if row["ic"] <= base / 2:
            return row["seconds"]
    return np.nan


def plot_all(ic_df, roll, curves, date):
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # 图 1：IC 衰减
    plt.figure(figsize=(7, 4))
    for code, g in ic_df.groupby("code"):
        g = g.sort_values("seconds")
        plt.plot(g["seconds"], g["ic"], marker="o", label=CODES.get(code, code))
        plt.plot(g["seconds"], g["rank_ic"], linestyle="--", alpha=0.6)
    plt.axhline(0, color="gray", lw=0.8)
    plt.xlabel("Holding horizon (seconds)")
    plt.ylabel("IC (solid) / RankIC (dashed)")
    plt.title(f"IC decay - {date}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "ic_decay.png", dpi=140)
    plt.close()

    # 图 2：滚动 IC
    plt.figure(figsize=(9, 4))
    for code, s in roll.items():
        plt.plot(range(len(s)), s.to_numpy(), label=CODES.get(code, code), lw=1)
    plt.axhline(0, color="gray", lw=0.8)
    plt.xlabel("Time index (30s)")
    plt.ylabel("Rolling IC (window=120)")
    plt.title(f"Rolling IC - {date}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "rolling_ic.png", dpi=140)
    plt.close()

    # 图 3：多空净值
    plt.figure(figsize=(9, 4))
    for code, c in curves.items():
        plt.plot(range(len(c)), c.to_numpy(), label=CODES.get(code, code), lw=1)
    plt.axhline(1, color="gray", lw=0.8)
    plt.xlabel("Time index (30s)")
    plt.ylabel("Cumulative NAV (long high OBI / short low OBI)")
    plt.title(f"Long-short NAV - {date}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "long_short.png", dpi=140)
    plt.close()


def main(date="20260113"):
    print("=" * 78)
    print(f"因子评价：五档等权 OBI    数据 {date}")
    print("=" * 78)

    panel = load_panel(date)
    print(f"样本 {len(panel):,} 行，{panel['time'].nunique()} 个时点，{panel['code'].nunique()} 只票\n")

    ic = ic_table(panel)
    ic.to_csv(FIG_DIR / "metrics.csv", index=False, encoding="utf-8-sig") if FIG_DIR.exists() else None
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    ic.to_csv(FIG_DIR / "metrics.csv", index=False, encoding="utf-8-sig")

    print("【1】IC 衰减表")
    piv = ic.pivot_table(index="h", columns="code", values="ic")
    print(piv.round(4).to_string())
    print()

    print("【2】h=1 的完整指标")
    sub = ic[ic["h"] == 1]
    for _, r in sub.iterrows():
        print(f"  {r['code']} {CODES.get(r['code'],'')}: IC={r['ic']:+.4f}  RankIC={r['rank_ic']:+.4f}  "
              f"t(naive)={r['t_naive']:+.2f}  t(自相关修正)={r['t_adj']:+.2f}  "
              f"因子自相关={r['autocorr']:.3f}  有效n={r['n_eff']:.0f}/{r['n']}")
    print()

    print("【3】半衰期（IC 降到 h=1 的一半所需时间）")
    for code in ic["code"].unique():
        hl = half_life(ic, code)
        print(f"  {code}: {hl if pd.notna(hl) else '未衰减到一半（>600 秒）'}")
    print()

    print("【4】高/低 OBI 分组（时序口径，分位 30%）")
    ls, curves = long_short(panel)
    for _, r in ls.iterrows():
        print(f"  {r['code']}: 高OBI组未来收益 {r['high_ret']:+.6f}  低OBI组 {r['low_ret']:+.6f}  "
              f"价差 {r['spread']:+.6f}（{r['n_high']}/{r['n_low']} 个点）")
    print()

    roll = rolling_ic(panel)
    print("【5】滚动 IC（窗口 120）")
    for code, s in roll.items():
        s2 = s.dropna()
        if len(s2):
            print(f"  {code}: 均值 {s2.mean():+.4f}  标准差 {s2.std():.4f}  "
                  f"为正 {(s2 > 0).mean():.1%}")
    print()

    plot_all(ic, roll, curves, date)
    print(f"图已保存：{FIG_DIR}")
    return ic, ls


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "20260113")
