# Order Book Reconstruction Project

> Reconstruct 10-level order book from tick-by-tick data, validate against official snapshots, and evaluate OBI factor performance.

[中文文档](README.md) | English

---

## Overview

This project reconstructs Level-3 order books from tick-by-tick order and trade data, validates reconstruction accuracy against official 10-level snapshots, and evaluates the predictive power of the Order Book Imbalance (OBI) factor.

**Target Securities**: 000001.SZ (Ping An Bank), 000002.SZ (Vanke A)

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/dominatorid001Jerry/orderbook-reconstruction.git
cd orderbook-reconstruction

# Install dependencies
pip install -r requirements.txt
```

### Run Demo

```bash
# Reconstruction + validation (with real data)
python validate_real.py 000001 20260410

# Full pipeline: reconstruction + validation + OBI + IC
python run_demo.py

# Synthetic data test (should output 169/169 matches)
python run_demo.py --sim
```

---

## Project Structure

```
orderbook-reconstruction/
├── src/                      # Core modules
│   ├── book.py              # Order book data structure (L3)
│   ├── replay_szse.py       # Shenzhen exchange reconstruction
│   ├── replay_sse.py        # Shanghai exchange reconstruction
│   ├── wind.py              # Wind data format parser
│   ├── data_loader.py       # Generic data loader
│   ├── validate.py          # Snapshot validation
│   └── factor.py            # OBI factor + IC calculation
│
├── data/                     # Market data (not included)
│   └── <date>/<code>/
│       ├── 逐笔委托.csv      # Tick-by-tick orders
│       ├── 逐笔成交.csv      # Tick-by-tick trades
│       └── 行情.csv          # 10-level snapshots
│
├── validate_real.py          # Main validation script
├── run_demo.py              # Demo with synthetic data
├── run_factor_real.py       # OBI factor evaluation
├── evaluate_factor.py       # 9 metrics + 3 charts
├── tune_obi.py              # Parameter sensitivity analysis
└── check_data.py            # Data integrity check

```

---

## Key Results

### Reconstruction Accuracy

| Date | Security | Match Rate | ≤1 Level | Avg Error |
|---|---|---|---|---|
| 2026-04-10 | 000001 | 67.2% | 91.6% | 0.57 |
| 2026-04-10 | 000002 | 72.9% | 93.6% | 0.44 |
| 2026-01-13 | 000001 | 47.6% | 79.5% | 0.92 |
| 2026-01-13 | 000002 | 47.5% | 78.2% | 0.94 |

**Finding**: Accuracy drops when event density doubles (4.9k → 9.9k ticks), likely due to sub-millisecond ordering issues (data precision: 10ms).

### OBI Factor Performance

| Parameter | 000001 | 000002 |
|---|---|---|
| n=5, h=30s | IC +0.078 | +0.063 |
| **n=10, h=30s** | **IC +0.094** | **IC +0.116** |
| Autocorrelation | 0.971 | 0.973 |
| t-stat (nominal) | 2.69 | 2.17 |
| t-stat (corrected) | **0.31** | **0.24** |
| Long-short spread | +2.32 bp | +2.20 bp |

**Conclusion**: OBI shows directional predictive power but is not statistically significant after autocorrelation adjustment. Economic value (+2 bp) is below transaction costs (~10 bp).

---

## Methodology

### 1. Order Book Reconstruction

**Shenzhen Exchange** (with order IDs):
- Add order → append to price-level queue
- Trade → remove from both sides using IDs
- Cancel → remove from one side

**Shanghai Exchange** (two modes):
- Mode A: Self-matching engine (47.56% accuracy)
- Mode B: Trade-only approximation (0.04% accuracy)

### 2. Validation

Compare reconstructed book with official 10-level snapshots:
- Level-by-level price & quantity comparison
- Match rate = (identical snapshots) / (total snapshots)
- Error metrics: average mismatch levels (out of 20)

### 3. OBI Factor

**Formula**:
```
OBI(n) = (Σ bid_qty[1:n] - Σ ask_qty[1:n]) / (Σ bid_qty[1:n] + Σ ask_qty[1:n])
```

**Parameters**:
- n: number of levels (5 or 10)
- h: forward return horizon (30s, 60s, etc.)

**Evaluation**:
- Time-series IC (same security, different times)
- Rolling RankIC (120-window)
- IC decay curve
- Quintile group returns

---

## Known Issues

1. **Low accuracy (47-67%)**: Sub-millisecond event ordering with 10ms data precision
2. **High autocorrelation**: 97% autocorrelation reduces effective sample size to 1.5%
3. **Small sample**: Only 2 securities × 2 days
4. **IC peaks at 90-150s**: 30s horizon polluted by microstructure noise

---

## Next Steps

1. **Improve accuracy to 99%**: Reverse-engineer snapshot-to-sequence mapping
2. **FF3/FF5 orthogonalization**: Check if OBI is style exposure in disguise
3. **Transaction cost backtest**: Add fees, slippage, limit-up/down constraints
4. **Expand sample**: More dates, more securities

---

## Data Format

This project uses Wind tick-by-tick data format (GBK encoding):

| Wind Field | Meaning | Example |
|---|---|---|
| 价格 `111000` | Price in 0.0001 yuan | 11.10 yuan |
| 委托类型 `0/1/U` | Order type: limit/market/best | |
| 成交代码 `0/C` | Exec type: trade/cancel | |
| 时间 `92500000` | Time in HHMMSSmmm | 09:25:00.000 |

**Data structure**:
```
data/<date>/<code>.<exchange>/
    ├── 逐笔委托.csv  # Orders
    ├── 逐笔成交.csv  # Trades (includes cancels)
    └── 行情.csv      # 10-level snapshots
```

---

## Citation

If you use this code in your research, please cite:

```bibtex
@misc{orderbook2026,
  title={Order Book Reconstruction and OBI Factor Evaluation},
  author={Jerry},
  year={2026},
  howpublished={\url{https://github.com/dominatorid001Jerry/orderbook-reconstruction}}
}
```

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Disclaimer

This project is for **educational and research purposes only**. The synthetic data in demo mode is artificially generated and does not represent real market behavior. Trading strategies based on this research require extensive additional validation and risk management.
