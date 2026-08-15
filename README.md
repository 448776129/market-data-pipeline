# Market Data Pipeline

通过 **GitHub Actions 自动拉取市场股票数据并保存到本地仓库**的项目。

使用 **yfinance** 从 Yahoo Finance 拉取**历史K线**、**当日行情**以及**非K线数据**（快照/财务/分析师/分红拆股），每只股票一个文件，按区域分目录保存到 `data/`，并由工作流自动提交回仓库。所有数据按市场拆分为独立 job，**异步并行**拉取。

## 核心特性

- **全自动**：GitHub Actions 按分段时间表定时运行，无需人工干预
- **多市场**：支持美股、港股、A股、韩股，按市场分目录
- **两类数据**：K线（CSV）与非K线（JSON）分开存放
- **异步并行**：每个市场独立 job，GitHub Actions 默认并行执行
- **增量更新**：当日数据自动与历史合并去重，避免节假日/周末缺数据
- **数据留空**：个股无数据的字段自动留空（`null`）

## 目录结构

```
.
├── config.py                     # 区域与符号配置
├── requirements.txt              # Python 依赖
├── scripts/
│   ├── fetch_universe.py         # 全市场股票列表拉取（美股右全量代码）
│   ├── fetch_historical.py       # 历史K线数据拉取（全量刷新）
│   ├── fetch_latest.py           # 当日K线数据增量更新
│   ├── fetch_meta.py             # 非K线数据（快照/财务/分析师等）
│   └── marketlib.py              # 共享工具（列表解析 + 分批）
└── .github/workflows/
    ├── market_data.yml           # 调度入口（按市场拆分 job）
    └── step-data.yml             # 可复用的数据拉取子工作流
```

## 数据布局

数据按区域分目录，每个区域内 K 线与非 K 线数据分开存放：

```
data/
├── universe/                     # 全市场股票列表
│   ├── us.csv                    # 全部美股代码（7600+ 只）
│   └── cn.csv                    # 全部A股代码（4200+ 只，含沪/深）
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

## 全市场模式

**美股**和**A股**均为**全市场模式**，股票代码不再硬编码：

- 美股（`us`）：由 `fetch_universe.py` 从公开清单动态拉取全部美股（约 7600+ 只），存入 `data/universe/us.csv`。
- A股（`cn`）：由内置的沪市（`.SS`）+ 深市（`.SZ`）代码清单组成（约 4200+ 只），存入 `data/universe/cn.csv`。

GitHub Actions 会先确保列表存在，再按列表分 **20 批**并行拉取每只股票的数据，避免单 job 超过 GitHub Actions 6 小时超时限制。

## 配置股票

编辑 [config.py](config.py) 中的 `REGIONS` 字典即可增删股票，无需改动脚本。**某区域列表留空（`[]`）即表示"全市场模式"**（从 universe 文件读取）：

```python
REGIONS = {
    "us": [],                     # 全市场模式：从 data/universe/us.csv 读取全部美股
    "hk": ["0700.HK", "9988.HK", ...],
    "cn": ["600519.SS", "000001.SZ", ...],
    "kr": ["005930.KS", "000660.KS", ...],
}
# 历史拉取范围与周期
HISTORY_PERIOD = "5y"
INTERVAL = "1d"
```

> 符号格式需符合 yfinance 约定：美股直接用 `AAPL`；港股加 `.HK`；A 股加 `.SS`（上交所）/ `.SZ`（深交所）；韩股加 `.KS`（如三星电子 `005930.KS`）。

## GitHub Actions（自动拉取）

| 任务 | 触发 | 说明 |
| ---- | ---- | ---- |
| 历史K线 | 每周一 01:00 UTC | 全量刷新近 5 年日线 |
| 当日K线 | 每天 13:00 UTC | 每日收盘后增量更新 |
| 非K线(meta) | 每天 13:00 UTC | 快照/财务/分析师/分红拆股 |

每个市场（`us` / `hk` / `cn` / `kr`）都有独立的 job，GitHub Actions 的独立 job 默认**并行执行**，从而实现各市场的**异步**拉取。其中**美股**（7600+ 只）和**A股**（4200+ 只）是全市场，会额外分 **20 批**并行拉取，避免单 job 超过 GitHub Actions 6 小时超时限制；港股/韩股各一个 job。拉取到的数据由工作流自动提交回仓库，保存在 `data/` 下。

### 手动触发

在仓库 **Actions** 页选择 `Market Data Pipeline` → **Run workflow**，通过 `mode` 输入选择：

- `historical`：运行全部历史K线拉取 job
- `daily`：运行全部当日K线增量 job
- `meta`：运行全部非K线数据拉取 job

## 本地运行

如需在本地手动拉取（不依赖 GitHub Actions）：

```bash
# 安装依赖
pip install -r requirements.txt

# 拉取全市场美股代码列表（写入 data/universe/us.csv）
python scripts/fetch_universe.py

# 拉取全部市场的历史K线数据
python scripts/fetch_historical.py

# 仅拉取指定区域（美股支持 --batch/--batches 分批）
python scripts/fetch_historical.py --region hk
python scripts/fetch_historical.py --region us --batch 0 --batches 20

# 当日K线数据增量更新（全部 / 指定区域 / 指定符号）
python scripts/fetch_latest.py
python scripts/fetch_latest.py --region hk
python scripts/fetch_latest.py --symbol TSLA

# 非K线数据（全部 / 指定区域）
python scripts/fetch_meta.py
python scripts/fetch_meta.py --region kr
```

## 说明

- 美股为全市场模式：先运行 `fetch_universe.py` 生成 `data/universe/us.csv`，再拉取数据；每个 fetch 脚本均支持 `--batch/--batches` 分批。
- `fetch_latest.py` 会拉取最近 5 天数据与已有文件合并、按日期去重，避免节假日/周末缺数据。
- `fetch_meta.py` 将非K线数据写入 `data/{region}/meta/`，与 K 线数据分开；没有数据的字段留空。
- 拉取到数据后通过 GitHub Actions 自动提交回仓库，历史记录可在 `data/` 下查看。