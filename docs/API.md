# API 文档 / API Documentation

## 核心模块 / Core Modules

### 1. OrderBook (`src/book.py`)

订单簿核心数据结构，维护价格优先-时间优先的 FIFO 队列。

Core order book data structure maintaining price-time priority FIFO queues.

#### 主要方法 / Main Methods

```python
class OrderBook:
    def add(self, seq, side, price, qty)
        """
        添加新委托 / Add new order
        
        Parameters:
            seq: 委托序号 / Order sequence number
            side: "B" (买) 或 "S" (卖) / "B" (buy) or "S" (sell)
            price: 委托价格 / Order price
            qty: 委托数量 / Order quantity
        """
    
    def reduce(self, seq, qty)
        """
        成交或撤单 / Execute or cancel order
        
        Parameters:
            seq: 委托序号 / Order sequence number
            qty: 减少数量 / Quantity to reduce
            
        Returns:
            float: 实际减少的数量 / Actual reduced quantity
        """
    
    def cancel(self, seq)
        """
        完全撤单 / Full cancellation
        
        Parameters:
            seq: 委托序号 / Order sequence number
        """
    
    def snapshot(self, levels=10)
        """
        获取当前盘口快照 / Get current market snapshot
        
        Parameters:
            levels: 档位数量 / Number of levels (default: 10)
            
        Returns:
            dict: {"bid_px": [...], "bid_qty": [...], 
                   "ask_px": [...], "ask_qty": [...]}
        """
```

---

### 2. SZRebooker (`src/replay_szse.py`)

深交所订单簿重建器。

Shenzhen Stock Exchange order book reconstructor.

```python
class SZRebooker:
    def __init__(self, code: str)
        """
        Parameters:
            code: 股票代码 / Stock code (e.g., "000001")
        """
    
    def feed_order(self, row)
        """
        处理委托事件 / Process order event
        
        Parameters:
            row: dict with keys {ApplSeqNum, Side, OrdType, Price, OrderQty}
        """
    
    def feed_trade(self, row)
        """
        处理成交事件 / Process trade event
        
        Parameters:
            row: dict with keys {ApplSeqNum, ExecType, TradeQty, 
                                 BidApplSeqNum, AskApplSeqNum}
        """
    
    def replay(self, orders_df, trades_df)
        """
        完整回放 / Full replay
        
        Parameters:
            orders_df: 逐笔委托 DataFrame / Tick-by-tick orders
            trades_df: 逐笔成交 DataFrame / Tick-by-tick trades
            
        Returns:
            list: 快照序列 / Snapshot sequence
        """
```

---

### 3. 校验模块 (`src/validate.py`)

```python
def compare(rebuilt, truth, levels=10)
    """
    逐档比对两个快照 / Compare two snapshots level by level
    
    Parameters:
        rebuilt: 重建的快照 / Reconstructed snapshot
        truth: 官方快照 / Official snapshot
        levels: 比对档位数 / Number of levels to compare
        
    Returns:
        int: 不匹配档数 (0-20) / Number of mismatched levels
    """

def report(errors)
    """
    生成校验报告 / Generate validation report
    
    Parameters:
        errors: list of int, 每个快照的错档数 / Error counts per snapshot
        
    Returns:
        dict: {"perfect": float, "within_1": float, "avg_error": float}
    """
```

---

### 4. 因子模块 (`src/factor.py`)

```python
def obi5(snapshot, n=5)
    """
    计算 n 档等权 OBI / Calculate n-level equal-weighted OBI
    
    Parameters:
        snapshot: dict with bid_px, bid_qty, ask_px, ask_qty
        n: 档位数 / Number of levels (default: 5)
        
    Returns:
        float: OBI 值 [-1, 1] / OBI value in [-1, 1]
    """

def ts_ic(factors, returns)
    """
    时序 IC / Time-series IC
    
    Parameters:
        factors: array of factor values
        returns: array of forward returns
        
    Returns:
        float: Spearman correlation
    """

def rolling_rank_ic(df, window=120)
    """
    滚动 RankIC / Rolling Rank IC
    
    Parameters:
        df: DataFrame with columns ["factor", "return"]
        window: 滚动窗口 / Rolling window size
        
    Returns:
        Series: 滚动 IC 序列 / Rolling IC series
    """
```

---

## 数据格式 / Data Format

### 输入 / Input

**逐笔委托 / Tick Orders**
```python
{
    "ApplSeqNum": int,        # 委托序号 / Order sequence number
    "TransactTime": int,      # 时间戳 (HHMMSSmmm) / Timestamp
    "Side": str,              # "B" 或 "S" / "B" or "S"
    "OrdType": str,           # "1" 市价 / "2" 限价 / "3" 本方最优
    "Price": float,           # 价格 / Price
    "OrderQty": float         # 数量 / Quantity
}
```

**逐笔成交 / Tick Trades**
```python
{
    "ApplSeqNum": int,        # 成交序号 / Trade sequence number
    "TransactTime": int,      # 时间戳 / Timestamp
    "ExecType": str,          # "4" 成交 / "F" 撤单
    "Price": float,           # 成交价 / Trade price
    "TradeQty": float,        # 成交量 / Trade quantity
    "BidApplSeqNum": int,     # 买方委托号 / Bid order ID
    "AskApplSeqNum": int      # 卖方委托号 / Ask order ID
}
```

### 输出 / Output

**快照 / Snapshot**
```python
{
    "bid_px": [11.10, 11.09, ...],   # 买价从高到低 / Bid prices descending
    "bid_qty": [1000, 2000, ...],    # 对应买量 / Corresponding quantities
    "ask_px": [11.11, 11.12, ...],   # 卖价从低到高 / Ask prices ascending
    "ask_qty": [1500, 1800, ...]     # 对应卖量 / Corresponding quantities
}
```

---

## 使用示例 / Usage Examples

### 完整流程 / Complete Pipeline

```python
from src.wind import load_folder
from src.replay_szse import SZRebooker
from src.validate import compare, report

# 1. 加载数据 / Load data
orders, trades, snaps = load_folder("data/20260410/000001.SZ")

# 2. 重建订单簿 / Reconstruct order book
rebooker = SZRebooker("000001")
rebuilt_snaps = rebooker.replay(orders, trades)

# 3. 校验 / Validate
errors = []
for i, official in enumerate(snaps):
    if i < len(rebuilt_snaps):
        err = compare(rebuilt_snaps[i], official)
        errors.append(err)

# 4. 报告 / Report
stats = report(errors)
print(f"完全匹配: {stats['perfect']:.1%}")
print(f"≤1 档误差: {stats['within_1']:.1%}")
print(f"平均错档: {stats['avg_error']:.2f}")
```

### 计算 OBI 因子 / Calculate OBI Factor

```python
from src.factor import obi5, ts_ic
import numpy as np

# 假设已有重建的快照序列 / Assume reconstructed snapshots
snapshots = [...]  # list of snapshot dicts

# 计算因子 / Calculate factors
factors = [obi5(s, n=10) for s in snapshots]

# 计算未来 30 秒收益 / Calculate 30s forward returns
returns = np.array([...])  # your return calculation

# 时序 IC / Time-series IC
ic = ts_ic(factors, returns)
print(f"Time-series IC: {ic:.4f}")
```

---

## 性能提示 / Performance Tips

1. **大数据集处理** / Large datasets:
   - 使用 `pyarrow` 格式存储中间结果
   - 分批处理多日数据
   
2. **内存优化** / Memory optimization:
   - 只保留必要的快照（如每分钟一个）
   - 及时释放不再使用的订单簿对象

3. **并行化** / Parallelization:
   - 不同股票可以并行重建
   - 使用 `multiprocessing` 处理多标的

---

## 常见问题 / FAQ

**Q: 为什么重建精度只有 47-67%？**
Why is reconstruction accuracy only 47-67%?

A: 数据时间精度为 10ms，同一毫秒内多个事件的排序无法确定。需要从快照反解真实序号映射。
Data time precision is 10ms; ordering of multiple events in the same millisecond is ambiguous. Need to reverse-engineer the true sequence mapping from snapshots.

**Q: 如何处理停牌和涨跌停？**
How to handle trading halts and limit up/down?

A: 停牌期间无委托成交流；涨跌停时委托可能无法全部成交。需在回测时加入这些约束。
No order/trade flow during halts; orders may not fully execute at limits. These constraints should be added in backtesting.

**Q: 沪市无委托号怎么重建？**
How to reconstruct SSE order book without order IDs?

A: 两种方法：(1) 自建撮合引擎推断；(2) 仅在成交时近似重建。见 `src/replay_sse.py`。
Two approaches: (1) Self-matching engine inference; (2) Trade-only approximation. See `src/replay_sse.py`.
