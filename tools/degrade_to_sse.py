# -*- coding: utf-8 -*-
"""把深市数据「降级」成沪市格式，用来开发和测试 replay_sse.py。

为什么要这么做：
    你手上只有深市数据（委托+成交都带委托号），但沪市很多数据源**只有逐笔成交、
    没有逐笔委托、成交里也没有委托号**。写完沪市代码你没法验证。

    这个脚本把深市数据里的「委托号」抹掉，只留价格/数量/方向/时间，
    模拟出沪市那种"看不见挂单"的处境。你的近似重建代码就能拿它测了。

用法：
    python tools/degrade_to_sse.py 20260113 000001
    输出 → data/sse_test/600000.SH/{逐笔成交.csv, 行情.csv}
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent      # 订单簿项目/
SRC_ROOT = HERE / "data"
OUT_ROOT = HERE / "data" / "sse_test"


def main(date="20260113", code="000001", fake_code="600000.SH"):
    src = SRC_ROOT / date / f"{code}.SZ"
    if not src.exists():
        print(f"找不到源数据：{src}")
        return
    dst = OUT_ROOT / fake_code
    dst.mkdir(parents=True, exist_ok=True)

    # ---- 成交流：只保留「成交」，抹掉委托号 ----
    t = pd.read_csv(src / "逐笔成交.csv", encoding="gbk", encoding_errors="ignore")
    n0 = len(t)
    t = t[t["成交代码"].astype(str) == "0"].copy()          # 去掉撤单（沪市可能根本没有）
    out = pd.DataFrame({
        "时间": t["时间"],
        "成交价格": t["成交价格"],
        "成交数量": t["成交数量"],
        "BS标志": t["BS标志"],                              # 主动买/卖，沪市有这个
    })
    out.to_csv(dst / "逐笔成交.csv", index=False, encoding="utf-8-sig")

    # ---- 行情：原样复制（十档快照，校验用）----
    snap = pd.read_csv(src / "行情.csv", encoding="gbk", encoding_errors="ignore")
    snap.to_csv(dst / "行情.csv", index=False, encoding="utf-8-sig")

    print(f"源：{src}")
    print(f"  成交 {n0:,} 条 → 只留成交 {len(out):,} 条（撤单已剔除）")
    print(f"  委托号已抹除：{['叫买序号','叫卖序号']} 不再存在")
    print(f"  快照 {len(snap):,} 张 原样保留")
    print(f"输出：{dst}")
    print("\n注意：这份数据**没有逐笔委托**，你的 replay_sse.py 只能走「近似重建」。")
    print("     验收标准不是 100%，而是：误差有多大、来自哪里。")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*args) if args else main()
