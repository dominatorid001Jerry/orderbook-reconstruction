# -*- coding: utf-8 -*-
"""CSV → Parquet 转换工具（专门处理行情数据的坑）。

为什么不用双击就能用的图形软件：
    逐笔数据的 CSV 动辄几个 GB，Excel/大部分转换器会直接崩，
    而且会把 '000001' 变成 1、把 GBK 中文列名变成乱码。

用法：
    python csv2parquet.py 输入.csv
    python csv2parquet.py 输入.csv 输出.parquet
    python csv2parquet.py data/                 # 整个目录批量转
    python csv2parquet.py 输入.csv --cast       # 自动把纯数字列转成数值类型
"""
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# 这些列永远保持字符串：一转成数字，前导零就没了
KEEP_STR = ("code", "symbol", "security", "id", "seq", "序号", "代码", "编号")


def detect_encoding(path: Path) -> str:
    """探测编码：先试 UTF-8（含 BOM），再试 GBK。"""
    raw = path.open("rb").read(200_000)
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def should_cast(col: str) -> bool:
    c = col.lower()
    return not any(k in c for k in KEEP_STR)


def cast_chunk(df: pd.DataFrame, cast: bool) -> pd.DataFrame:
    if not cast:
        return df
    for col in df.columns:
        if not should_cast(col):
            continue
        s = df[col]
        num = pd.to_numeric(s, errors="coerce")
        # 只有「全部能转成数字」才转，避免把 '10.01元' 这种搞坏
        if num.notna().all() and len(s):
            df[col] = num
    return df


def convert_one(src: Path, dst: Path = None, batch=1_000_000, compression="zstd", cast=False):
    dst = dst or src.with_suffix(".parquet")
    enc = detect_encoding(src)
    t0 = time.time()
    writer = None
    nrows = 0
    try:
        reader = pd.read_csv(src, dtype=str, encoding=enc, chunksize=batch,
                             low_memory=False, on_bad_lines="warn")
        for chunk in reader:
            chunk = cast_chunk(chunk, cast)
            tbl = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(dst, tbl.schema, compression=compression)
            writer.write_table(tbl)
            nrows += len(chunk)
    finally:
        if writer is not None:
            writer.close()

    src_mb = src.stat().st_size / 1024 / 1024
    dst_mb = dst.stat().st_size / 1024 / 1024
    print(f"  {src.name} [{enc}] {nrows:,} 行  "
          f"{src_mb:.1f}MB → {dst_mb:.1f}MB ({dst_mb / max(src_mb, 1e-9):.0%})  "
          f"{time.time() - t0:.1f}s")
    return dst


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return
    target = Path(argv[1])
    cast = "--cast" in argv
    args = [a for a in argv[2:] if not a.startswith("--")]
    out = Path(args[0]) if args else None

    if target.is_dir():
        files = sorted(target.glob("*.csv"))
        if not files:
            print(f"{target} 下没有 csv")
            return
        print(f"批量转换 {len(files)} 个文件：")
        for f in files:
            convert_one(f, f.with_suffix(".parquet"), cast=cast)
    else:
        convert_one(target, out, cast=cast)


if __name__ == "__main__":
    main(sys.argv)
