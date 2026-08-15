"""股票区域与符号配置。

按区域划分市场数据，每个区域对应 data/ 下的一个子目录。
新增或调整股票时只需修改本文件。
"""

from __future__ import annotations

# 区域 -> 符号列表
# 符号需符合 yfinance 的 ticker 格式：
#   - 美股: 如 AAPL、MSFT、TSLA
#   - 港股: 如 0700.HK、9988.HK
#   - A股:  如 600519.SS、000001.SZ
#   - 韩股: 如 005930.KS（三星电子）、000660.KS（SK海力士）
#
# 若某区域的符号列表留空（[]），则该市场被当作"全市场"模式：
# 从 universe 文件（data/universe/{region}.csv）读取全部股票代码。
REGIONS: dict[str, list[str]] = {
    "us": [],  # 全市场模式：从 data/universe/us.csv 读取全部美股
    "hk": [],  # 全市场模式：从 data/universe/hk.csv 读取全部港股
    "cn": [],  # 全市场模式：从 data/universe/cn.csv 读取全部A股(沪+深)
    "kr": [],  # 全市场模式：从 data/universe/kr.csv 读取全部韩股
}

# 历史数据拉取范围（yfinance period 参数）
HISTORY_PERIOD = "5y"
# K线周期（yfinance interval 参数）
INTERVAL = "1d"

# 数据根目录
DATA_DIR = "data"
# K线数据子目录（每只股票一个文件）
KLINE_SUBDIR = "kline"
# 非K线数据（快照/财务/分析师等）子目录（每只股票一个文件）
META_SUBDIR = "meta"
# 全市场股票列表子目录；文件名 = {region}.csv（如 us.csv、cn.csv）
UNIVERSE_SUBDIR = "universe"
# 各区域全市场列表文件名
UNIVERSE_FILES = {
    "us": "us.csv",
    "cn": "cn.csv",
    "hk": "hk.csv",
    "kr": "kr.csv",
}

# 请求间隔（秒）：控制对 Yahoo 的请求频率，避免触发限流导致 429/404
REQUEST_DELAY = 2
# 单只股票请求的最大重试次数（遇瞬时网络/限流错误时指数退避重试）
MAX_RETRIES = 3

# 全市场股票列表的数据源（供 fetch_universe.py 使用）
# us: 每行一个美股代码
# hk: 港股代码清单（code 列），需加 .HK
# kr: KRX 缓存（动态日期），Code 列加 .KS
UNIVERSE_SOURCES = {
    "us": "https://raw.githubusercontent.com/abbadata/stock-tickers/main/data/allsymbols.txt",
    "hk": "https://raw.githubusercontent.com/darr/stock_code/master/hk_stock_code.csv",
}

# 分钟级K线（主要针对纳指100成分股）
# 纳指100成分股清单文件名（data/universe/ 下）
NASDAQ100_FILE = "nasdaq100.csv"
# 标普500成分股清单文件名（data/universe/ 下）
SP500_FILE = "sp500.csv"
# 分钟级K线子目录（按周期分目录，每只股票一个文件）
INTRADAY_M1_SUBDIR = "kline_1m"
INTRADAY_M15_SUBDIR = "kline_15m"
INTRADAY_M1H_SUBDIR = "kline_1h"
# 分钟级K线各周期的 yfinance period（1m 仅保留约7天，15m 约60天，1h 约730天）
INTRADAY_PERIOD = {"1m": "5d", "15m": "2mo", "1h": "6mo"}