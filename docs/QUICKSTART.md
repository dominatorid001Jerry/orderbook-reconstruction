# 快速开始 / Quick Start

## 10 分钟上手 / Get Started in 10 Minutes

### 步骤 1：安装 / Step 1: Installation

```bash
# 克隆仓库 / Clone repository
git clone https://github.com/dominatorid001Jerry/orderbook-reconstruction.git
cd orderbook-reconstruction

# 安装依赖 / Install dependencies
pip install -r requirements.txt
```

### 步骤 2：测试运行 / Step 2: Test Run

```bash
# 使用合成数据测试（应输出 169/169）
# Test with synthetic data (should output 169/169)
python run_demo.py --sim
```

**预期输出 / Expected Output:**
```
第 1 部分：重建 + 校验
  000001 平安银行  委托 1,870 / 成交(含撤单) 1,635 / 快照 169
    正确版：   完全一致 169/169 (100.00%)  ← 应该看到这个
    
第 2 部分：OBI 的 IC / RankIC（2 只票）
  (B) 时序 IC：
        000001  IC=+0.0390  RankIC=+0.0569
        000002  IC=+0.1059  RankIC=+0.0877
```

如果看到 `169/169 (100.00%)`，说明安装成功！

If you see `169/169 (100.00%)`, installation is successful!

---

### 步骤 3：准备数据 / Step 3: Prepare Your Data

#### 数据格式 / Data Format

项目需要三个 CSV 文件：

Project requires three CSV files:

```
data/
└── 20260410/           # 日期文件夹 / Date folder
    └── 000001.SZ/      # 股票代码文件夹 / Stock code folder
        ├── 逐笔委托.csv
        ├── 逐笔成交.csv
        └── 行情.csv     # 可选，用于校验 / Optional, for validation
```

#### 必需字段 / Required Fields

**逐笔委托.csv** (Orders):
- 交易所委托号 / ApplSeqNum
- 时间 / TransactTime
- 委托价格 / Price
- 委托数量 / OrderQty
- 委托代码 / Side (B/S 或 1/2)
- 委托类型 / OrdType

**逐笔成交.csv** (Trades):
- 成交编号 / ApplSeqNum
- 时间 / TransactTime
- 成交价格 / Price
- 成交数量 / TradeQty
- 成交代码 / ExecType (4=成交, F=撤单)
- 叫买序号 / BidApplSeqNum
- 叫卖序号 / AskApplSeqNum

#### 数据检查 / Data Check

```bash
# 检查数据完整性 / Check data integrity
python check_data.py 000001
```

**可能的结果 / Possible Results:**
- ✅ **可完整重建** / Can fully reconstruct
- ⚠️ **只能近似** / Can only approximate (缺委托号 / missing order IDs)
- ❌ **不能重建** / Cannot reconstruct (字段缺失 / missing fields)

---

### 步骤 4：运行验证 / Step 4: Run Validation

```bash
# 重建 + 校验（需要真实数据）
# Reconstruct + validate (requires real data)
python validate_real.py 000001 20260410
```

**输出示例 / Output Example:**
```
000001 平安银行 2026-04-10
  委托 57,145 / 成交 48,996 / 快照 4,808
  
  完全一致:   3,232 / 4,808 (67.2%)
  ≤1 档误差:  4,404 / 4,808 (91.6%)
  ≤2 档误差:  4,707 / 4,808 (97.9%)
  
  平均错档: 0.57 / 20
```

---

### 步骤 5：计算因子 / Step 5: Calculate Factors

```bash
# OBI 因子 + IC 评估 / OBI factor + IC evaluation
python run_factor_real.py

# 完整评估（9 项指标 + 3 张图）
# Full evaluation (9 metrics + 3 charts)
python evaluate_factor.py
```

**生成文件 / Generated Files:**
```
data/figs/
├── ic_decay.png          # IC 衰减曲线 / IC decay curve
├── rolling_ic.png        # 滚动 IC / Rolling IC
├── long_short.png        # 多空净值 / Long-short equity
└── metrics.csv           # 9 项指标汇总 / 9 metrics summary
```

---

## 常用脚本 / Common Scripts

| 脚本 / Script | 用途 / Purpose | 用法 / Usage |
|---|---|---|
| `run_demo.py --sim` | 合成数据测试 / Synthetic test | 验证代码正确性 |
| `check_data.py 000001` | 数据体检 / Data check | 判断能否重建 |
| `validate_real.py 000001 20260410` | 重建+校验 / Reconstruct+validate | 评估重建精度 |
| `run_factor_real.py` | 因子 IC / Factor IC | 快速看 IC |
| `evaluate_factor.py` | 完整评估 / Full evaluation | 生成报告 |
| `tune_obi.py` | 参数调优 / Parameter tuning | n × h 敏感性 |

---

## 下一步 / Next Steps

### 选项 A：扩展样本 / Option A: Expand Sample
```bash
# 添加更多日期和股票 / Add more dates and stocks
mkdir -p data/20260415/000003.SZ
# ... 放入数据文件
python validate_real.py 000003 20260415
```

### 选项 B：调整参数 / Option B: Tune Parameters
```bash
# 测试不同的 n 和 h / Test different n and h
python tune_obi.py
# 生成热力图和最优参数 / Generate heatmap and optimal parameters
```

### 选项 C：改进算法 / Option C: Improve Algorithm
```python
# 修改 src/replay_szse.py
# 例如：添加同毫秒事件的排序逻辑
# Modify src/replay_szse.py
# E.g., add sub-millisecond event ordering logic
```

---

## 故障排除 / Troubleshooting

### 问题 1：`ImportError: No module named 'pandas'`

**解决方案 / Solution:**
```bash
pip install pandas numpy pyarrow matplotlib py7zr
```

### 问题 2：`UnicodeDecodeError: 'utf-8' codec can't decode`

**原因 / Cause:** Wind 数据是 GBK 编码

**解决方案 / Solution:** 代码已自动处理，确保使用 `src/wind.py` 加载数据

### 问题 3：重建精度为 0%

**可能原因 / Possible Causes:**
1. 数据缺少委托编号（沪市 B 模式）
2. 时间戳格式不匹配
3. 价格单位未转换

**诊断 / Diagnosis:**
```bash
python check_data.py <code>
# 查看输出的诊断信息 / Check diagnostic output
```

### 问题 4：IC 为 NaN

**原因 / Cause:** 
- 样本量太小（< 30）
- 因子值全部相同
- 收益数据缺失

**解决方案 / Solution:**
```python
# 检查因子和收益的分布 / Check factor and return distribution
import pandas as pd
df = pd.read_csv("data/panel_sample.csv")
print(df["factor"].describe())
print(df["return"].describe())
```

---

## 性能基准 / Performance Benchmarks

| 任务 / Task | 数据量 / Data Size | 耗时 / Time |
|---|---|---|
| 重建 1 天 1 只票 / Reconstruct 1 day 1 stock | ~10 万笔 / 100k ticks | ~5 秒 |
| 校验 5000 个快照 / Validate 5000 snapshots | 10 档 / 10 levels | ~2 秒 |
| 计算 1 天 OBI / Calculate 1 day OBI | 5000 个点 / 5000 points | <1 秒 |
| 完整评估（2 天 2 只票）/ Full eval (2 days 2 stocks) | ~40 万笔 / 400k ticks | ~30 秒 |

**硬件参考 / Hardware:** Intel i7-10700, 16GB RAM, SSD

---

## 获取帮助 / Get Help

- **文档** / Documentation: [docs/API.md](API.md)
- **问题报告** / Issues: [GitHub Issues](https://github.com/dominatorid001Jerry/orderbook-reconstruction/issues)
- **讨论** / Discussions: [GitHub Discussions](https://github.com/dominatorid001Jerry/orderbook-reconstruction/discussions)

---

**祝研究顺利！ / Happy researching!** 🚀
