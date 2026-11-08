# -*- coding: utf-8 -*-
"""真实数据读取层：把各家数据商的 CSV/parquet 翻译成项目内部统一表。

设计原则：**这一层之外，任何代码都不允许出现中文列名或数据商私有字段名。**

支持的目录约定（放 data/ 下，文件名包含代码即可）：
    data/000001_orders.csv      逐笔委托
    data/000001_trades.csv      逐笔成交
    data/000001_snaps.parquet   10 档快照（可选，有才能校验）

也支持同义列名（见 ALIASES），所以你拿到别人的数据一般不用改文件。
"""
import re
from pathlib import Path

import pandas as pd

# 内部统一列名 -> 可能出现的各种写法（大小写、下划线、中文）
ALIASES = {
    "ChannelNo": ["channelno", "channel_no", "channel", "频道号", "频道"],
    "ApplSeqNum": ["applseqnum", "appl_seq_num", "seqno", "seq", "序号", "应用序号", "委托序号", "成交序号"],
    "SecurityID": ["securityid", "security_id", "code", "symbol", "证券代码", "股票代码"],
    "TransactTime": ["transacttime", "transact_time", "time", "时间", "成交时间", "委托时间"],
    "Price": ["price", "价格", "成交价", "委托价"],
    "OrderQty": ["orderqty", "order_qty", "数量", "委托量", "委托数量"],
    "TradeQty": ["tradeqty", "trade_qty", "成交量", "成交数量"],
    "Side": ["side", "方向", "买卖方向", "bs"],
    "OrdType": ["ordtype", "ord_type", "委托类型", "订单类型"],
    "ExecType": ["exectype", "exec_type", "成交类型", "执行类型"],
    "BidApplSeqNum": ["bidapplseqnum", "bid_appl_seq_num", "买方委托序号", "买方序号"],
    "AskApplSeqNum": ["askapplseqnum", "ask_appl_seq_num", "卖方委托序号", "卖方序号"],
}


def _norm(s):
    return re.sub(r"[\s_\-]", "", str(s)).lower()


def _pick(df, canonical):
    """在一堆列名里找到 canonical 对应的那一列。"""
    want = {_norm(a) for a in ALIASES.get(canonical, [canonical])} | {_norm(canonical)}
    for c in df.columns:
        if _norm(c) in want:
            return c
    return None


def to_hhmmssmmm(s: pd.Series) -> pd.Series:
    """时间统一成 int HHMMSSmmm。

    真实数据里时间可能是 '09:25:00.123'、'2026-01-05 09:25:00.123'、或已经是 92500123。
    """
    if pd.api.types.is_numeric_dtype(s):
        return s.astype("int64")
    txt = s.astype(str).str.strip()
    out = pd.Series(0, index=s.index, dtype="int64")
    # 'HH:MM:SS(.mmm)'
    m = txt.str.extract(r"(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?")
    ok = m[0].notna()
    if ok.any():
        ms = m[3].fillna("0").str.ljust(3, "0").astype(int)
        out.loc[ok] = (m.loc[ok, 0].astype(int) * 10_000_000
                       + m.loc[ok, 1].astype(int) * 100_000
                       + m.loc[ok, 2].astype(int) * 1_000
                       + ms)
    # 'HHMMSSmmm' 纯数字字符串
    rest = ~ok
    if rest.any():
        digits = txt[rest].str.replace(r"\D", "", regex=True).str.zfill(9).str[:9]
        out.loc[rest] = pd.to_numeric(digits, errors="coerce").fillna(0).astype("int64")
    return out


def normalize(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """统一列名。kind = 'orders' / 'trades'。"""
    need = (["ChannelNo", "ApplSeqNum", "TransactTime", "Price", "OrderQty"]
            if kind == "orders" else
            ["ChannelNo", "ApplSeqNum", "TransactTime", "Price", "TradeQty"])
    out = {}
    for c in need + ["Side", "OrdType", "ExecType", "BidApplSeqNum", "AskApplSeqNum", "SecurityID"]:
        src = _pick(df, c)
        if src is not None:
            out[c] = df[src]
    res = pd.DataFrame(out)
    if "ChannelNo" not in res:
        res["ChannelNo"] = 1
    res["TransactTime"] = to_hhmmssmmm(res["TransactTime"])
    res["ApplSeqNum"] = res["ApplSeqNum"].astype("int64")
    if "SecurityID" in res:
        # 坑：CSV 读进来时 '000001' 会被当成数字 1，前导零全丢。
        res["SecurityID"] = (res["SecurityID"].astype(str)
                             .str.extract(r"(\d+)")[0].str.zfill(6))
    return res


def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(path)
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="utf-8", errors="ignore")


def _find(root: Path, code: str, tag: str):
    pats = [f"*{code}*{tag}*", f"*{tag}*{code}*"]
    hits = []
    for p in pats:
        hits += [f for f in root.glob(p) if f.is_file()]
    return sorted(set(hits))


def load_code(code: str, root="data"):
    """返回 {'orders': df, 'trades': df, 'snaps': df|None}；找不到返回 None。

    优先识别 Wind 的目录结构（<日期>/<代码>.SZ/逐笔委托.csv …），
    其次才按扁平文件名匹配。
    """
    root = Path(root)
    if not root.exists():
        return None

    # ---- 1) Wind 目录结构 ----
    try:
        from wind import find_folder, load_folder
        folder = find_folder(root, code)
        if folder is not None:
            return load_folder(folder)
    except ImportError:
        pass

    # ---- 2) 扁平文件 ----
    of = _find(root, code, "orders") or _find(root, code, "order") or _find(root, code, "委托")
    tf = _find(root, code, "trades") or _find(root, code, "trade") or _find(root, code, "成交")
    sf = _find(root, code, "snaps") or _find(root, code, "snap") or _find(root, code, "快照")
    if not of or not tf:
        return None
    orders = normalize(_read_any(of[0]), "orders")
    trades = normalize(_read_any(tf[0]), "trades")
    snaps = _read_any(sf[0]) if sf else None
    return {"orders": orders, "trades": trades, "snaps": snaps,
            "files": {"orders": str(of[0]), "trades": str(tf[0]),
                      "snaps": str(sf[0]) if sf else None}}
