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
    "hk": [
        "0700.HK",
        "9988.HK",
        "3690.HK",
        "0941.HK",
    ],
    "cn": [
        "600519.SS",
        "000001.SZ",
        "601318.SS",
        "300750.SZ",
    ],
    "kr": [
        "005930.KS",  # 三星电子
        "000660.KS",  # SK海力士
        "373220.KS",  # LG新能源
        "035420.KS",  # NAVER
    ],
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
# 全市场股票列表子目录与文件名
UNIVERSE_SUBDIR = "universe"
UNIVERSE_FILE = "us.csv"