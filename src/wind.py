# -*- coding: utf-8 -*-
"""Wind 格式逐笔数据的解析（这份样本用的就是它）。

文件结构：
    <某天>/<代码>.<交易所>/逐笔委托.csv
                          /逐笔成交.csv
                          /行情.csv      ← 十档快照

字段与交易所原始字段的差别（这是最花时间的地方）：
- 价格是「元 × 10000」，111000 表示 11.10 元
- 委托类型用 0/1/U，不是交易所的 1/2/3
- 成交代码用 0/C，不是交易所的 4/F
- 撤单记录在**成交流**里，成交代码=C，价格恒为 0
"""
import io
from pathlib import Path

import pandas as pd

PRICE_SCALE = 10_000          # 价格单位：元 × 10000

# 委托类型：Wind -> 交易所口径
ORDTYPE_MAP = {"0": "2", "1": "1", "U": "3", "T": "3"}
# 成交代码：Wind -> 交易所口径（0=成交，C=撤单）
EXECTYPE_MAP = {"0": "4", "C": "F"}

ORDER_COLS = {
    "交易所委托号": "ApplSeqNum",
    "时间": "TransactTime",
    "委托价格": "Price",
    "委托数量": "OrderQty",
    "委托代码": "Side",
    "委托类型": "OrdType",
}
TRADE_COLS = {
    "成交编号": "ApplSeqNum",
    "时间": "TransactTime",
    "成交价格": "Price",
    "成交数量": "TradeQty",
    "成交代码": "ExecType",
    "叫卖序号": "AskApplSeqNum",
    "叫买序号": "BidApplSeqNum",
    "BS标志": "Aggressor",
}


def _read(path: Path) -> pd.DataFrame:
    """先严格解码、再解析——不能用 errors='ignore' 探测，否则 GBK 会被当成 UTF-8 静默读成乱码。"""
    raw = Path(path).read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="ignore")
    return pd.read_csv(io.StringIO(text))


def load_orders(folder: Path) -> pd.DataFrame:
    df = _read(folder / "逐笔委托.csv")
    out = df[list(ORDER_COLS)].rename(columns=ORDER_COLS).copy()
    out["Price"] = out["Price"].astype("float64") / PRICE_SCALE
    out["OrderQty"] = out["OrderQty"].astype("float64")
    out["OrdType"] = out["OrdType"].astype(str).str.upper().map(ORDTYPE_MAP).fillna("2")
    out["Side"] = out["Side"].astype(str).str.upper()
    out["TransactTime"] = out["TransactTime"].astype("int64")
    out["ApplSeqNum"] = out["ApplSeqNum"].astype("int64")
    out["ChannelNo"] = 1
    return out[["ChannelNo", "ApplSeqNum", "TransactTime", "Price", "OrderQty", "Side", "OrdType"]]


def load_trades(folder: Path) -> pd.DataFrame:
    df = _read(folder / "逐笔成交.csv")
    out = df[list(TRADE_COLS)].rename(columns=TRADE_COLS).copy()
    out["Price"] = out["Price"].astype("float64") / PRICE_SCALE
    out["TradeQty"] = out["TradeQty"].astype("float64")
    out["ExecType"] = out["ExecType"].astype(str).str.upper().map(EXECTYPE_MAP).fillna("4")
    out["BidApplSeqNum"] = out["BidApplSeqNum"].fillna(0).astype("int64")
    out["AskApplSeqNum"] = out["AskApplSeqNum"].fillna(0).astype("int64")
    out["Aggressor"] = out["Aggressor"].fillna("N").astype(str).str.strip().replace("", "N")
    out["TransactTime"] = out["TransactTime"].astype("int64")
    out["ApplSeqNum"] = out["ApplSeqNum"].astype("int64")
    out["ChannelNo"] = 1
    return out[["ChannelNo", "ApplSeqNum", "TransactTime", "Price", "TradeQty",
                "ExecType", "BidApplSeqNum", "AskApplSeqNum", "Aggressor"]]


def load_snaps(folder: Path, levels=10) -> pd.DataFrame:
    """十档快照。列名是 申卖价1..10 / 申卖量1..10 / 申买价1..10 / 申买量1..10。"""
    df = _read(folder / "行情.csv")
    out = pd.DataFrame({"TransactTime": df["时间"].astype("int64")})
    for i in range(1, levels + 1):
        out[f"ask_px{i}"] = df[f"申卖价{i}"].astype("float64") / PRICE_SCALE
        out[f"ask_qty{i}"] = df[f"申卖量{i}"].astype("float64")
        out[f"bid_px{i}"] = df[f"申买价{i}"].astype("float64") / PRICE_SCALE
        out[f"bid_qty{i}"] = df[f"申买量{i}"].astype("float64")
    if "成交价" in df.columns:
        out["last"] = df["成交价"].astype("float64") / PRICE_SCALE
    return out


def load_folder(folder) -> dict:
    folder = Path(folder)
    return {"orders": load_orders(folder), "trades": load_trades(folder),
            "snaps": load_snaps(folder) if (folder / "行情.csv").exists() else None,
            "files": {"orders": str(folder / "逐笔委托.csv"),
                      "trades": str(folder / "逐笔成交.csv"),
                      "snaps": str(folder / "行情.csv") if (folder / "行情.csv").exists() else None}}


def find_folder(root, code: str):
    """在 root 下找形如 000001.SZ / 000001 的目录。"""
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_dir() and (p.name == code or p.name.startswith(f"{code}.")):
            if (p / "逐笔委托.csv").exists() and (p / "逐笔成交.csv").exists():
                return p
    return None

