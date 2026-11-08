# -*- coding: utf-8 -*-
"""用真实的 Wind 数据做校验：重建出来的盘口 vs 官方十档快照。

这是整个项目的「验收考试」——只有这张表全对，重建才算成功。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from replay_szse import SZRebooker  # noqa: E402
from validate import compare, report  # noqa: E402
from wind import load_folder  # noqa: E402


def snaps_to_truth(df, levels=10):
    """把快照 DataFrame 转成 compare() 认识的格式（bid_px/bid_qty 两个平行列表）。"""
    out = []
    for _, r in df.iterrows():
        item = {"bid_px": [], "bid_qty": [], "ask_px": [], "ask_qty": []}
        for i in range(1, levels + 1):
            if r[f"bid_px{i}"] > 0:
                item["bid_px"].append(r[f"bid_px{i}"])
                item["bid_qty"].append(r[f"bid_qty{i}"])
            if r[f"ask_px{i}"] > 0:
                item["ask_px"].append(r[f"ask_px{i}"])
                item["ask_qty"].append(r[f"ask_qty{i}"])
        out.append(item)
    return out


def main(code="000001", date="20260410"):
    folder = Path("data") / date / f"{code}.SZ"
    if not folder.exists():
        print(f"找不到 {folder}")
        return

    d = load_folder(folder)
    o, t, s = d["orders"], d["trades"], d["snaps"]
    print(f"{code}: 委托 {len(o):,} / 成交 {len(t):,} / 快照 {len(s):,}")

    s = s[s["TransactTime"] >= 93000000].reset_index(drop=True)
    grid = s["TransactTime"].tolist()
    print(f"只比较连续竞价（9:30 之后）的快照：{len(grid)} 个")
    print("  说明：集合竞价期间行情表给的是『竞价参考价/匹配量』，不是真实挂单，不能拿来比。")

    rb = SZRebooker().run(o, t, snap_times=grid)
    print(f"打点 {len(rb.records)} 个，事件数 {rb.event_count:,}")
    print(f"未匹配：成交 {rb.miss['trade']} 次，撤单 {rb.miss['cancel']} 次，委托 {rb.miss['order']} 次")

    truth = snaps_to_truth(s)
    df = compare(rb.records, truth, levels=10)
    report(df, code)

    # 只看「收盘前」的准确率（午盘常有一字板、停牌等特殊情况）
    bad = df[df["diff_levels"] > 0]
    if len(bad):
        print(f"\n  有差异的快照 {len(bad)} 个，前 5 个：")
        print(bad.head(5).to_string(index=False))
        k = int(bad.index[0])
        print(f"\n  第 {k} 个快照（时间 {grid[k]}）")
        print(f"    官方买: {list(zip(truth[k]['bid_px'][:3], truth[k]['bid_qty'][:3]))}")
        print(f"    重建买: {rb.records[k][1]['bid'][:3]}")
        print(f"    官方卖: {list(zip(truth[k]['ask_px'][:3], truth[k]['ask_qty'][:3]))}")
        print(f"    重建卖: {rb.records[k][1]['ask'][:3]}")
    return df


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "000001"
    date = sys.argv[2] if len(sys.argv) > 2 else "20260410"
    main(code, date)
