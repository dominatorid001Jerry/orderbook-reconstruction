# -*- coding: utf-8 -*-
"""在真实数据上算「五档等权 OBI」的 IC / RankIC。

两只票 → 只能算「时序 IC」（每只票自己和自己比）。
截面 IC 需要几十只票，这里只做演示并说明为什么退化。
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from factor import (add_forward_return, build_panel, ic_series, make_grid,  # noqa: E402
                    rolling_rank_ic, summarize, ts_ic)
from wind import load_folder  # noqa: E402

pd.set_option("display.width", 130)
pd.set_option("display.unicode.east_asian_width", True)

CODES = {"000001": "平安银行", "000002": "万科A"}
DATE = "20260113"


def main(date=DATE, step=30):
    print("=" * 76)
    print(f"五档等权 OBI 的 IC / RankIC    数据：{date}    采样间隔：{step}s")
    print("=" * 76)

    sims = {}
    for code in CODES:
        folder = HERE / "data" / date / f"{code}.SZ"
        if not folder.exists():
            print(f"缺数据：{folder}")
            return
        d = load_folder(folder)
        sims[code] = {"orders": d["orders"], "trades": d["trades"]}
        print(f"  {code} {CODES[code]}: 委托 {len(d['orders']):,} / 成交 {len(d['trades']):,}")

    grid = make_grid(step_sec=step)
    panel = build_panel(sims, grid)
    panel = add_forward_return(panel, horizon=1).dropna(subset=["obi", "mid", "ret"])
    print(f"\n  样本 {len(panel):,} 行，{panel['time'].nunique()} 个时点，每点 {len(panel)/panel['time'].nunique():.0f} 只票")

    # ---------- (A) 截面 IC：2 只票必然退化 ----------
    print("\n  (A) 截面 IC（2 只票 → 每个时点只有 2 个点）")
    cs = ic_series(panel, min_stocks=2)
    if len(cs):
        vals = sorted(set(cs["ic"].round(6)))
        print(f"      截面数 {len(cs)}，IC 取值集合 {vals[:6]}")
        print("      相关系数只能是 ±1 —— 没有统计意义。")

    # ---------- (B) 时序 IC：两只票各自算 ----------
    print("\n  (B) 时序 IC（这才是 2 只票该做的）")
    df = ts_ic(panel, min_obs=60)
    if df.empty:
        print("      样本不足")
    else:
        df["名称"] = df["code"].map(CODES)
        print(df[["code", "名称", "n", "ic", "rank_ic"]].to_string(index=False,
              float_format=lambda v: f"{v:+.4f}"))
        print(f"\n      均值：IC={df['ic'].mean():+.4f}  RankIC={df['rank_ic'].mean():+.4f}")

    # ---------- (C) 滚动 RankIC：稳定性 ----------
    print("\n  (C) 滚动 RankIC（窗口 120 个采样点）")
    for code in panel["code"].unique():
        r = rolling_rank_ic(panel, code=code, window=120).dropna()
        if r.empty:
            continue
        print(f"      {code} {CODES.get(code,'')}: 均值 {r.mean():+.4f}  "
              f"标准差 {r.std():.4f}  为正 {(r>0).mean():.1%}  "
              f"区间 [{r.min():+.3f}, {r.max():+.3f}]")

    # ---------- (D) 分时段：因子会不会衰减 ----------
    print("\n  (D) 分时段时序 IC（看因子在一天里稳不稳）")
    panel["小时"] = (panel["time"] // 10000000).astype(int)
    for code in panel["code"].unique():
        sub = panel[panel["code"] == code]
        rows = []
        for h, g in sub.groupby("小时"):
            g = g.dropna(subset=["obi", "ret"])
            if len(g) < 30 or g["obi"].std() == 0 or g["ret"].std() == 0:
                continue
            rows.append({"小时": h, "IC": g["obi"].corr(g["ret"]),
                         "RankIC": g["obi"].rank().corr(g["ret"].rank())})
        if rows:
            t = pd.DataFrame(rows)
            print(f"\n      {code} {CODES.get(code,'')}:")
            print(t.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    out = HERE / "data" / f"ic_{date}.csv"
    if not df.empty:
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n  已保存：{out}")
    return df


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DATE)
