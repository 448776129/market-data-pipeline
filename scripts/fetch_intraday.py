"""分钟级K线数据拉取脚本。

从 Yahoo Finance 拉取分钟级K线（1分钟、1小时），其中 5m/15m/30m 为雅虎
不提供的历史周期，由 1m 数据代码重采样计算得到。每只股票、每个周期各写入
一个 CSV 文件，按区域与周期分目录存放：
    data/{region}/kline_1m/{symbol}.csv
    data/{region}/kline_5m/{symbol}.csv    (由 1m 计算)
    data/{region}/kline_15m/{symbol}.csv   (由 1m 计算)
    data/{region}/kline_30m/{symbol}.csv   (由 1m 计算)
    data/{region}/kline_1h/{symbol}.csv

范围：
    - --index：拉取指定指数成分股（csi300/csi500/ndx100/sp500/hsi）
    - --region：按区域（默认按 config.REGIONS 全市场，需 universe 文件）

增量查重：只拉取已有文件最后时间点之后的新数据，与已有文件按时间点合并去重
（追加而非覆盖），重复运行只补新增时间点，不会每天全量重拉。

用法：
    python scripts/fetch_intraday.py --index sp500            # 标普500成分股
    python scripts/fetch_intraday.py --index csi300           # 沪深300成分股
    python scripts/fetch_intraday.py --region us --batch 0 --batches 20
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import marketlib  # noqa: E402

COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
INDEX_COL = "Datetime"

# 周期 -> 子目录名
SUBDIR = {
    "1m": config.INTRADAY_M1_SUBDIR,
    "5m": config.INTRADAY_M5_SUBDIR,
    "15m": config.INTRADAY_M15_SUBDIR,
    "30m": config.INTRADAY_M30_SUBDIR,
    "1h": config.INTRADAY_M1H_SUBDIR,
}
# 直接由雅虎拉取的周期（1m 额外派生 5m/15m/30m，1h 雅虎原生提供）
SOURCE_INTERVALS = ["1m", "1h"]


def output_path(region: str, symbol: str, interval: str) -> Path:
    return ROOT / config.DATA_DIR / region / SUBDIR[interval] / f"{symbol}.csv"


def derive_from_1m(region: str, symbol: str, target: str) -> Path | None:
    """从 1 分钟K线重采样计算出 15m/30m 周期，写盘并返回输出路径。

    雅虎不提供 15m/30m 历史数据，这里按标准 OHLCV 聚合：
    Open=首根开盘、High=区间最高、Low=区间最低、Close=末根收盘、Volume=求和，
    Adj Close 取区间最后一根的 Close。时间桶对齐到 15/30 分钟边界。
    """
    rule = config.INTRADAY_DERIVED.get(target)
    if not rule:
        return None
    src = output_path(region, symbol, "1m")
    out = output_path(region, symbol, target)
    out.parent.mkdir(parents=True, exist_ok=True)

    df = marketlib.read_kline(src, index_col=INDEX_COL)
    if df is None or df.empty:
        return out if out.exists() else None

    # 标准 OHLCV 聚合
    agg = df.resample(rule).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    # 丢弃没有成交的空桶
    agg = agg.dropna(subset=["Close"])
    if agg.empty:
        return out if out.exists() else None

    agg["Adj Close"] = df["Close"].resample(rule).last()
    agg = agg[COLS]

    merged = marketlib.merge_kline(out, agg, COLS, index_col=INDEX_COL)
    print(
        f"  [派生] {symbol} {target} (由 1m 计算) -> {out.relative_to(ROOT)} (共 {len(merged)} 行)",
        flush=True,
    )
    return out


def fetch_symbol(region: str, symbol: str, interval: str) -> Path | None:
    """增量拉取单只股票指定周期的分钟K线，追加去重后返回输出路径；失败返回 None。

    增量策略：若文件已存在，只拉取最后时间点之前缓冲段之后的新数据，避免每天
    全量重拉；首次运行或文件为空时拉取 config.INTRADAY_PERIOD 的全量范围。
    """
    out = output_path(region, symbol, interval)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    existing = marketlib.read_kline(out, index_col=INDEX_COL)

    if existing is None or existing.empty:
        # 首次/空文件：全量拉取
        df = ticker.history(
            period=config.INTRADAY_PERIOD[interval],
            interval=interval,
            auto_adjust=False,
        )
        mode_label = "全量"
    else:
        # 增量：只拉取最后时间点之前缓冲段（含回看，覆盖修订）之后的数据
        last_dt = existing.index.max()
        start = (last_dt - pd.Timedelta(days=config.INTRADAY_BUFFER_DAYS)).to_pydatetime()
        df = ticker.history(
            start=start,
            interval=interval,
            auto_adjust=False,
        )
        mode_label = "增量"

    if df is None or df.empty:
        print(f"  [跳过] {symbol} {interval}: 无新数据返回", flush=True)
        return out if out.exists() else None

    cols = [c for c in COLS if c in df.columns]
    merged = marketlib.merge_kline(out, df, cols, index_col=INDEX_COL)
    print(
        f"  [{mode_label}] {symbol} {interval} -> {out.relative_to(ROOT)} (共 {len(merged)} 行)",
        flush=True,
    )

    # 由 1m 派生 15m/30m（雅虎不提供，代码重采样计算）
    if interval == "1m":
        for target in sorted(config.INTRADAY_DERIVED):
            derive_from_1m(region, symbol, target)

    return out


def run(
    region: str | None,
    intervals: list[str],
    index: str | None = None,
    batch: int = 0,
    batches: int = 1,
) -> int:
    targets: list[tuple[str, str]] = []
    if index:
        reg, syms = marketlib.load_index_symbols(index)
        syms = marketlib.slice_batch(syms, batch, batches)
        targets.extend((reg, s) for s in syms)
    elif region:
        syms = marketlib.load_symbols(region)
        syms = marketlib.slice_batch(syms, batch, batches)
        targets.extend((region, s) for s in syms)
    else:
        for reg in config.REGIONS:
            syms = marketlib.load_symbols(reg)
            syms = marketlib.slice_batch(syms, batch, batches)
            targets.extend((reg, s) for s in syms)

    if not targets:
        print("未找到匹配的符号/区域/指数", file=sys.stderr)
        return 1

    failed: list[str] = []
    for reg, symbol in targets:
        for interval in intervals:
            try:
                marketlib.run_with_retry(fetch_symbol, reg, symbol, interval)
            except Exception as exc:  # noqa: BLE001 - 单只失败不中断整体
                print(f"  [失败] {reg} {symbol} {interval}: {exc}", flush=True)
                failed.append(f"{reg}:{symbol}@{interval}")
            time.sleep(config.REQUEST_DELAY)

    if failed:
        print(f"失败 {len(failed)} 项: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取分钟级K线（1m/1h）")
    parser.add_argument(
        "--region",
        choices=list(config.REGIONS),
        help="仅处理指定区域",
    )
    parser.add_argument(
        "--index",
        choices=sorted(config.INDEX_CONFIG),
        help="拉取指定指数成分股（csi300/csi500/ndx100/sp500/hsi）",
    )
    parser.add_argument(
        "--interval",
        choices=SOURCE_INTERVALS + ["all"],
        default="all",
        help="K线周期（默认 all=1m+1h；15m/30m 由 1m 自动计算，无需手动选择）",
    )
    parser.add_argument("--batch", type=int, default=0, help="当前批次（0 起）")
    parser.add_argument("--batches", type=int, default=1, help="总批次数")
    args = parser.parse_args()
    intervals = SOURCE_INTERVALS if args.interval == "all" else [args.interval]
    return run(args.region, intervals, args.index, args.batch, args.batches)


if __name__ == "__main__":
    sys.exit(main())