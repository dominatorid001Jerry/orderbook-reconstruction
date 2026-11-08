# -*- coding: utf-8 -*-
"""把深市数据降级成「沪市 A 模式」：保留委托流和撤单，但抹掉**成交**的委托号。

为什么这么设计：
    上交所 L2 的常见形态是——逐笔委托有编号，撤单能对上，
    但**逐笔成交里不告诉你买卖双方是谁**，只能靠「价格 + 时间优先」推断。

用法：
    python tools/degrade_mode_a.py 20260113 000001
输出：
    data/sse_test_a/600000.SH/{逐笔委托.csv, 逐笔成交.csv, 行情.csv}
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
SRC_ROOT = HERE / "data"


def main(date="20260113", code="000001", fake="600000.SH"):
    src = SRC_ROOT / date / f"{code}.SZ"
    dst = SRC_ROOT / "sse_test_a" / fake
    if not src.exists():
        print(f"找不到 {src}")
        return
    dst.mkdir(parents=True, exist_ok=True)

    # 委托：原样保留（沪市有委托流）
    o = pd.read_csv(src / "逐笔委托.csv", encoding="gbk", encoding_errors="ignore")
    o.to_csv(dst / "逐笔委托.csv", index=False, encoding="utf-8-sig")

    # 成交：只把「成交」那部分的双方委托号抹掉；
    #      「撤单」那部分保留委托号（沪市撤单通常能对上）
    t = pd.read_csv(src / "逐笔成交.csv", encoding="gbk", encoding_errors="ignore")
    is_deal = t["成交代码"].astype(str) == "0"
    t.loc[is_deal, "叫卖序号"] = 0
    t.loc[is_deal, "叫买序号"] = 0
    t = t.drop(columns=[c for c in t.columns if str(c).startswith("Unnamed")], errors="ignore")
    t.to_csv(dst / "逐笔成交.csv", index=False, encoding="utf-8-sig")

    # 快照：原样
    s = pd.read_csv(src / "行情.csv", encoding="gbk", encoding_errors="ignore")
    s.to_csv(dst / "行情.csv", index=False, encoding="utf-8-sig")

    print(f"源 {src}")
    print(f"  委托 {len(o):,} 条（原样）")
    print(f"  成交 {int(is_deal.sum()):,} 条（委托号已抹掉）")
    print(f"  撤单 {int((~is_deal).sum()):,} 条（保留委托号）")
    print(f"输出 {dst}")
    print("\n这份数据 = 沪市 A 模式：有委托流、撤单能对上、成交只能推断。")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*args) if args else main()
