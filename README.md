# Market Data Pipeline

通过 **GitHub Actions 自动拉取指定指数成分股的行情数据并保存到本地仓库**的项目。

使用 **yfinance** 从 Yahoo Finance 拉取**日K线**、**1分钟K线**、**1小时K线**，并通过 **1分钟K线重采样计算 5、15、30分钟K线**，每只股票一个文件，按区域分目录保存到 `data/`，并由工作流自动提交回仓库。数据按指数拆分为独立 job，**异步并行**拉取。

## 核心特性

- **全自动**：GitHub Actions 按分段时间表定时运行，无需人工干预
- **指数驱动**：只拉取用户配置的 5 个指数成分股，而非全市场
- **多周期**：日K线、1分钟/5分钟/15分钟/半小时/1小时K线分开存放
- **异步并行**：每个指数独立 job，GitHub Actions 默认并行执行
- **增量更新**：只拉取上次之后的新数据，与已有文件合并去重（追加而非全量重拉）
- **派生K线**：5m/15m/30m 由 1m 重采样计算（雅虎不提供这些历史周期）
- **动态接口**：配套 Cloudflare Worker，可随时查询任意股票的K线数据

## 支持的指数

| 指数 | 代码 | 区域 | 说明 |
| ---- | ---- | ---- | ---- |
| 沪深300 | `csi300` | cn | 沪深两市总市值排名前 300 名大盘股 |
| 中证500 | `csi500` | cn | 排名 301～800 名的中盘股 |
| 纳指100 | `ndx100` | us | 纳斯达克 100 只大盘股 |
| 标普500 | `sp500` | us | 标普综合500 |
| 恒生指数 | `hsi` | hk | 香港恒生指数 |

## 目录结构

```
.
├── config.py                     # 区域、指数与数据源配置
├── requirements.txt              # Python 依赖
├── scripts/
│   ├── fetch_universe.py         # 指数成分股清单拉取
│   ├── fetch_historical.py       # 日K线数据拉取（全量/增量）
│   ├── fetch_latest.py           # 当日日K线增量更新
│   ├── fetch_intraday.py         # 分钟K线（1m/1h）拉取
│   └── marketlib.py              # 共享工具（列表解析 + 合并去重 + 分批）
├── api/                          # Cloudflare Worker 动态接口
│   └── src/index.js
└── .github/workflows/
    ├── market_data.yml           # 调度入口（按指数拆分 job）
    └── step-data.yml             # 可复用的数据拉取子工作流
```

## 数据布局

数据按区域分目录，K 线按周期拆分子目录：

```
data/
├── universe/                     # 指数成分股清单
│   ├── csi300.csv                # 沪深300（300 只）
│   ├── csi500.csv                # 中证500
│   ├── sp500.csv                 # 标普500
│   ├── nasdaq100.csv             # 纳指100
│   └── hsi.csv                   # 恒生指数
├── cn/                           # A股
│   ├── kline/                    # 日K线，如 600519.SS.csv
│   ├── kline_1m/                 # 1分钟K线
│   ├── kline_5m/                 # 5分钟K线（由 1m 计算）
│   ├── kline_15m/                # 15分钟K线（由 1m 计算）
│   ├── kline_30m/                # 半小时K线（由 1m 计算）
│   └── kline_1h/                 # 1小时K线
├── us/                           # 美股
│   ├── kline/                    # 如 AAPL.csv
│   ├── kline_1m/
│   ├── kline_5m/
│   ├── kline_15m/
│   ├── kline_30m/
│   └── kline_1h/
└── hk/                           # 港股
    ├── kline/                    # 如 0700.HK.csv
    ├── kline_1m/
    ├── kline_5m/
    ├── kline_15m/
    ├── kline_30m/
    └── kline_1h/
```

### 入库文件字段说明

每只股票一个 CSV，按周期分目录存放。日K线与分钟K线字段一致，仅时间索引列名不同（日线为 `Date`，分钟线为 `Datetime`）：

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `Date` / `Datetime` | 时间 | 时间索引列。日线为交易日期（`YYYY-MM-DD`）；分钟线为带时分秒的时间戳 |
| `Open` | float | 开盘价 |
| `High` | float | 最高价 |
| `Low` | float | 最低价 |
| `Close` | float | 收盘价 |
| `Adj Close` | float | 复权收盘价（考虑除权除息/分红后的调整价） |
| `Volume` | float | 成交量（股数） |

CSV 以该时间索引为第一列，其余列顺序固定为 `Open, High, Low, Close, Adj Close, Volume`。分钟K线的 `Datetime` 精确到分钟，用于按时间点去重合并。

> **5m/15m/30m 派生说明**：雅虎不提供 5、15、半小时K线历史，采集端用 1 分钟数据按标准方式重采样计算 —— `Open`=区间首根开盘价、`High`=区间最高价、`Low`=区间最低价、`Close`=区间末根收盘价、`Volume`=区间内成交量求和，`Adj Close` 取区间末根 `Close`。时间桶对齐到 5/15/30 分钟边界。因此这些衍生的历史深度与 1m 一致（雅虎 1m 约保留 5~7 天）。

### 数据口径与注意事项

#### 1）时间戳按「K线起始时间」标注

雅虎（以及多数行情源）用**每根K线的起始时间**打标，而非结束时间：

- **1h 周期**：美股正式盘中为 **9:30–16:00 美东**，1h 最后一根K线标为 `15:30`（9:30、10:30 … 15:30），但实际覆盖 **15:30–16:00** 的收盘段，其 `Close` 即 16:00 官方收盘价。**数据没有丢失**，只是显示为起始时间。
- **1m 周期**：盘中最后一根标为 `15:59`（覆盖 15:59–16:00），盘后第一根从 `16:00` 开始。
- **1d 周期**：`Date` 为交易日，`Close` 为该日 16:00 收盘价。

> 因此查询 1h 数据时，出现 `15:30` 而非 `16:00` 是正常的，代表 15:30–16:00 这一根。

#### 2）美股盘前盘后（延长时段）数据

雅虎的**分钟级数据包含延长交易时段**，但分周期差异很大：

| 周期 | 是否含盘前/盘后 | 说明 |
| ---- | ---- | ---- |
| `1m` | ✅ 含 | 美股 1m 覆盖 **4:00–20:00 美东**（盘前 4:00–9:30、盘中 9:30–16:00、盘后 16:00–20:00） |
| `5m` / `15m` / `30m` | ✅ 含 | 由 1m 重采样派生，自然继承延长时段 |
| `1h` | ❌ 不含 | 雅虎 60m 只给盘中（9:30–16:00 ET），但含 15:30–16:00 收盘bar |
| `1d` | ❌ 不含 | 日K为盘中聚合，不含延长时段 |

> **注意**：上述延长时段特性仅对**美股**成立；A股/港股盘中时间不同（A股有午休，港股 9:30–16:00），且其分钟数据是否含延长时段取决于雅虎数据源，使用前请以实际数据为准。

### 外部验证接口：新浪财经实时行情（含盘后）

作为**数据校验/快照接口**（非本管道的入库数据源），可直接调用新浪财经的实时行情接口核对美股价格，且**原生返回盘后（延长时段）涨跌与成交量**，用于验证雅虎数据的一致性：

```
GET https://hq.sinajs.cn/list=gb_mu
Headers: Referer: https://finance.sina.com.cn
```

- `list` 参数为美股符号，格式 `gb_<小写代码>`，如 `gb_mu`（美光）、`gb_aapl`（苹果）。
- 返回为 GBK 编码的 `var hq_str_gb_mu="字段,逗号分隔";` 文本，需按 `，`（逗号）拆分字段。

**字段说明（按索引）：**

| 索引 | 字段 | 示例（MU） |
| ---- | ---- | ---- |
| 0 | 名称 | 美光 |
| 1 | 最新价 | 971.66 |
| 2 | 涨跌幅% | 2.30 |
| 3 | 数据时间 | 2026-08-15 07:59:58 |
| 4 | 涨跌额 | 21.83 |
| 5/6/7 | 开盘 / 最高 / 最低 | 979.32 / 984.00 / 956.20 |
| 8/9 | 52周高 / 低 | 1254.85 / 112.93 |
| 10/11 | 成交量 / 10日均量 | 27881135 / 37046306 |
| 12 | 市值 | 1097386117035 |
| 13/14 | EPS / PE | 44.80 / 21.69 |
| 21 | **盘后价** | 972.98 |
| 22 | **盘后涨跌幅%** | 0.14 |
| 23 | **盘后涨跌额** | 1.32 |
| 24 | **盘后时间** | Aug 14 07:59PM EDT |
| 25 | 收盘时间 | Aug 14 04:00PM EDT |
| 26 | 昨收 | 949.83 |
| 27 | **盘后成交量** | 643491 |

> **说明**：新浪的 K 线序列接口（`US_MinKService` / `US_HisKLineService`，即页面 5/15/30/60 分图表数据源）目前返回 `null` / `Service not valid`，旧端点已废弃，**暂无法**用它获取含延长时段的 K 线序列；本接口仅用于核对**当前实时价格与盘后快照**。

## 配置指数

编辑 [config.py](config.py) 中的 `INDEX_CONFIG`（指数 -> 区域）与 `INDEX_SOURCES`（成分股数据源即可增删指数，无需改动脚本：

```python
INDEX_CONFIG = {
    "csi300": {"file": "csi300.csv", "region": "cn"},
    "csi500": {"file": "csi500.csv", "region": "cn"},
    "ndx100": {"file": "nasdaq100.csv", "region": "us"},
    "sp500":  {"file": "sp500.csv", "region": "us"},
    "hsi":    {"file": "hsi.csv", "region": "hk"},
}
```

成分股清单由 `fetch_universe.py` 从公开数据源（yfiua/index-constituents，符号与 Yahoo Finance 完全一致）更新到 `data/universe/`。

> 符号格式遵循 yfinance 约定：美股直接用 `AAPL`；港股加 `.HK`；A股加 `.SS`（上交所）/`.SZ`（深交所）。

## GitHub Actions（自动拉取）

| 任务 | 触发（北京时间） | 说明 |
| ---- | ---- | ---- |
| 指数清单 | 手动触发 | 更新 5 个指数成分股（暂不定时） |
| 历史日K线 | 手动触发一次 | 近 5 年日线全量入库（之后靠增量更新） |
| 历史分钟K线 | 手动触发一次 | 1m/1h 全量入库，并自动计算 5m/15m/30m |
| 日K / 分钟K 增量 | 每 1 小时 | 增量更新（追加去重），5m/15m/30m 由 1m 计算 |

> 指数清单、历史全量都在**手动触发**时执行（见下方「手动触发」），无需定时；之后每天每 1 小时自动增量更新即可。

每个指数（`csi300` / `csi500` / `ndx100` / `sp500` / `hsi`）都有独立的 job，GitHub Actions 的独立 job 默认**并行执行**，从而实现各指数的**异步**拉取。拉取到的数据由工作流自动提交回仓库，保存在 `data/` 下。

### 手动触发

在仓库 **Actions** 页选择 `Market Data Pipeline` → **Run workflow**，通过 `mode` 与 `index` 输入选择：

- `mode`：`historical`（日K全量）/ `daily`（日K增量）/ `minute`（分钟K）/ `universe`（指数清单）
- `index`：`all`（全部指数）或单个指数名

首次部署时建议先手动触发：
1. `mode=universe` 拉取成分股清单
2. `mode=historical` 全量入库日K线
3. `mode=minute` 全量入库 1m/1h K线（自动计算并入库 5m/15m/30m）

之后由分段时间表自动增量更新。

### 动态接口（Cloudflare Worker）

仓库内的 `api/` 是一个 Cloudflare Worker，免费托管（无需服务器），直接读取本仓库 `data/` 下的 CSV 并转成 JSON 返回，供量化系统调用。

**在线接口地址：**

```
https://stockapi.365200.xyz/kline?symbol=AAPL&interval=1d&limit=5
```

**响应示例（JSON）：**

```json
{
  "symbol": "AAPL",
  "region": "us",
  "interval": "1d",
  "count": 5,
  "order": "asc",
  "data": [
    { "Date": "2026-08-11", "Open": 217.9, "High": 219.7, "Low": 216.3, "Close": 218.7, "Adj Close": 218.7, "Volume": 41000000 },
    { "Date": "2026-08-12", "Open": 219.0, "High": 220.5, "Low": 217.8, "Close": 219.9, "Adj Close": 219.9, "Volume": 39500000 }
  ]
}
```

**参数说明：**

| 参数 | 必填 | 默认 | 说明 |
| ---- | ---- | ---- | ---- |
| `symbol` | 是 | — | 股票代码，如 `AAPL` / `0700.HK` / `600519.SS` |
| `interval` | 否 | `1d` | `1d`(日线) / `1m`(1分钟) / `5m`(5分钟) / `15m`(15分钟) / `30m`(半小时) / `1h`(1小时) |
| `start` | 否 | — | 起始日期 `YYYY-MM-DD`（含） |
| `end` | 否 | — | 结束日期 `YYYY-MM-DD`（含） |
| `limit` | 否 | 全部 | 最多返回行数（返回最新 N 条） |
| `order` | 否 | `asc` | `asc`(时间升序) / `desc`(最新在前) |
| `format` | 否 | `json` | `json` / `csv`（返回原始 CSV 文本） |

返回的 `data` 数组元素字段与入库 CSV 列一致（日线含 `Date`，分钟线含 `Datetime`）。`interval=5m/15m/30m` 返回由 1m 重采样计算的历史（与 1m 深度一致，约 5~7 天）；`interval=1h` 返回雅虎原生小时K线。

部署方式见 [api/README.md](api/README.md)。接口首页（`https://stockapi.365200.xyz/`）为项目介绍与 API 文档页面。

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 拉取指数成分股清单（写入 data/universe/）
python scripts/fetch_universe.py
python scripts/fetch_universe.py --index csi300   # 仅指定指数

# 拉取日K线（默认增量追加；--full 强制全量）
python scripts/fetch_historical.py                # 全部指数
python scripts/fetch_historical.py --index sp500  # 标普500成分股
python scripts/fetch_historical.py --index csi300 --full

# 当日日K线增量更新
python scripts/fetch_latest.py --index hsi

# 分钟K线（1m/1h 雅虎拉取，5m/15m/30m 自动由 1m 计算）
python scripts/fetch_intraday.py --index ndx100
python scripts/fetch_intraday.py --index csi300 --interval 1h
```

## 说明

- 所有 fetch 脚本均支持 `--index`；`--batch/--batches` 可将成分股分批，避免单 job 超过 GitHub Actions 6 小时超时限制（成分股较多时按需分批）。
- 数据增量拉取均带回看缓冲，合并去重，覆盖除权/分红导致的修订；重复运行不会重复写入。
- 拉取到数据后通过 GitHub Actions 自动提交回仓库，历史记录可在 `data/` 下与 git 历史中查看。