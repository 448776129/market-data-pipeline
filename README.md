# Market Data Pipeline

自动化市场数据流水线：通过 **yfinance** 从 Yahoo Finance 拉取**历史**、**当日**行情数据以及**非K线数据**（快照/财务/分析师/分红拆股），每只股票一个文件，按区域分目录存放于 `data/`。GitHub Actions 按分段时间表运行——K线与非K线数据在每个市场均有独立 job，并行（异步）处理。

## 目录结构

```
.
├── config.py                     # 区域与符号配置
├── requirements.txt              # Python 依赖
├── scripts/
│   ├── fetch_historical.py       # 历史K线数据拉取（全量刷新）
│   ├── fetch_latest.py           # 当日K线数据增量更新
│   └── fetch_meta.py             # 非K线数据（快照/财务/分析师等）
└── .github/workflows/
    ├── market_data.yml           # 调度入口（按市场拆分 job）
    └── step-data.yml             # 可复用的数据拉取子工作流
```

## 数据布局

数据按区域分目录，每个区域内 K 线与非 K 线数据分开存放：

```
data/
├── us/                          # 美股
│   ├── kline/                   # K线数据，如 AAPL.csv
│   └── meta/                    # 非K线数据，如 AAPL.json
├── hk/                          # 港股
│   ├── kline/
│   └── meta/
├── cn/                          # A股
│   ├── kline/
│   └── meta/
└── kr/                          # 韩股
    ├── kline/
    └── meta/
```

- **K线 CSV** 列为：`Date, Open, High, Low, Close, Adj Close, Volume`。
- **meta JSON** 包含：行情快照 `info`、分红 `dividends`、拆股 `splits`、资本利得 `capital_gains`、财务 `financials/balancesheet/cashflow`、分析师目标价与评级、大股东/机构持股等。没有数据的字段留空（`null`）。

## 配置股票

编辑 [config.py](config.py) 中的 `REGIONS` 字典即可增删股票，无需改动脚本：

```python
REGIONS = {
    "us": ["AAPL", "MSFT", "TSLA", ...],
    "hk": ["0700.HK", "9988.HK", ...],
    "cn": ["600519.SS", "000001.SZ", ...],
    "kr": ["005930.KS", "000660.KS", ...],
}
# 历史拉取范围与周期
HISTORY_PERIOD = "5y"
INTERVAL = "1d"
```

> 符号格式需符合 yfinance 约定：美股直接用 `AAPL`；港股加 `.HK`；A 股加 `.SS`（上交所）/ `.SZ`（深交所）；韩股加 `.KS`（如三星电子 `005930.KS`）。

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 拉取全部市场的历史K线数据
python scripts/fetch_historical.py

# 仅拉取指定区域
python scripts/fetch_historical.py --region us

# 当日K线数据增量更新（全部 / 指定区域 / 指定符号）
python scripts/fetch_latest.py
python scripts/fetch_latest.py --region hk
python scripts/fetch_latest.py --symbol TSLA

# 非K线数据（全部 / 指定区域）
python scripts/fetch_meta.py
python scripts/fetch_meta.py --region kr
```

## GitHub Actions

| 任务 | 触发 | 说明 |
| ---- | ---- | ---- |
| 历史K线 | 每周一 01:00 UTC | 全量刷新近 5 年日线 |
| 当日K线 | 每天 13:00 UTC | 每日收盘后增量更新 |
| 非K线(meta) | 每天 13:00 UTC | 快照/财务/分析师/分红拆股 |

每个市场（`us` / `hk` / `cn` / `kr`）都有独立的 job，GitHub Actions 的独立 job 默认**并行执行**，从而实现各市场的**异步**拉取。历史、当日、meta 任务分别有 `historical-*`、`daily-*`、`meta-*` 各四个 job。

### 手动触发

在仓库 **Actions** 页选择 `Market Data Pipeline` → **Run workflow**，通过 `mode` 输入选择：

- `historical`：运行全部历史K线拉取 job
- `daily`：运行全部当日K线增量 job
- `meta`：运行全部非K线数据拉取 job

## 说明

- `fetch_latest.py` 会拉取最近 5 天数据与已有文件合并、按日期去重，避免节假日/周末缺数据。
- `fetch_meta.py` 将非K线数据写入 `data/{region}/meta/`，与 K 线数据分开；没有数据的字段留空。
- 拉取到数据后通过 GitHub Actions 自动提交回仓库，历史记录可在 `data/` 下查看。