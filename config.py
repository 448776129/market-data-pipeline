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

# 指数成分股清单（按用户配置拉取，替代全市场）
# index 名 -> (清单文件名, 所属区域)
# 清单文件位于 data/universe/ 下，由 fetch_universe.py 从数据源更新
INDEX_CONFIG: dict[str, dict] = {
    "csi300": {"file": "csi300.csv", "region": "cn"},   # 沪深300（A股）
    "csi500": {"file": "csi500.csv", "region": "cn"},   # 中证500（A股）
    "ndx100": {"file": "nasdaq100.csv", "region": "us"},  # 纳指100
    "sp500": {"file": "sp500.csv", "region": "us"},       # 标普500
    "hsi": {"file": "hsi.csv", "region": "hk"},           # 恒生指数
}

# 指数成分股清单数据源（供 fetch_universe.py 使用）
# 来自 yfiua/index-constituents，符号与 Yahoo Finance 完全一致
INDEX_SOURCES = {
    "csi300": "https://yfiua.github.io/index-constituents/constituents-csi300.csv",
    "csi500": "https://yfiua.github.io/index-constituents/constituents-csi500.csv",
    "nasdaq100": "https://yfiua.github.io/index-constituents/constituents-nasdaq100.csv",
    "sp500": "https://yfiua.github.io/index-constituents/constituents-sp500.csv",
    "hsi": "https://yfiua.github.io/index-constituents/constituents-hsi.csv",
}

# 拉取的范围：默认按 INDEX_CONFIG 拉取指数成分股（用户配置）
# 关闭全市场模式：REGIONS 全部保持空即可，由 --index 指定指数
# 分钟级K线子目录（按周期分目录，每只股票一个文件）
INTRADAY_M1_SUBDIR = "kline_1m"
INTRADAY_M1H_SUBDIR = "kline_1h"
# 分钟级K线各周期的 yfinance period（1m 仅保留约7天，1h 约730天）
INTRADAY_PERIOD = {"1m": "5d", "1h": "6mo"}
# 分钟级K线增量拉取时的回看缓冲天数：覆盖数据修订（除权/分红/错误修正）
INTRADAY_BUFFER_DAYS = 2