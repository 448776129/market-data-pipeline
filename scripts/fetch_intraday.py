"""分钟级K线数据拉取脚本。

从 Yahoo Finance 拉取纳指100成分股的分钟级K线（1分钟、15分钟），
每个周期、每只股票各写入一个 CSV 文件，按区域与周期分目录存放：
    data/us/kline_1m/{symbol}.csv
    data/us/kline_15m/{symbol}.csv

用法：
    python scripts/fetch_intraday.py                 # 拉取1m + 15m
    python scripts/fetch_intraday.py --interval 15m  # 仅拉取15m
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import marketlib  # noqa: E402

COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]

# 周期 -> 子目录名
SUBDIR = {
    "1m": config.INTRADAY_M1_SUBDIR,
    "15m": config.INTRADAY_M15_SUBDIR,
}


def load_symbols() -> list[str]:
    """读取纳指100成分股清单。"""
    path = ROOT / config.DATA_DIR / config.UNIVERSE_SUBDIR / config.NASDAQ100_FILE
    if not path.exists():
        print(f"  [警告] 纳指100清单不存在: {path.relative_to(ROOT)}", file=sys.stderr)
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def output_path(symbol: str, interval: str) -> Path:
    return ROOT / config.DATA_DIR / "us" / SUBDIR[interval] / f"{symbol}.csv"


def fetch_symbol(symbol: str, interval: str) -> Path | None:
    """拉取单只股票指定周期的分钟K线，返回输出路径；失败返回 None。"""
    out = output_path(symbol, interval)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    df = ticker.history(
        period=config.INTRADAY_PERIOD[interval],
        interval=interval,
        auto_adjust=False,
    )

    if df is None or df.empty:
        print(f"  [跳过] {symbol} {interval}: 无数据返回", flush=True)
        return None

    cols = [c for c in COLS if c in df.columns]
    df = df[cols].copy()
    df.index.name = "Datetime"
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df.to_csv(out, encoding="utf-8")
    print(
        f"  [完成] {symbol} {interval} -> {out.relative_to(ROOT)} ({len(df)} 行)",
        flush=True,
    )
    return out


def run(intervals: list[str]) -> int:
    symbols = load_symbols()
    print(f"[纳指100] 共 {len(symbols)} 只成分股，周期 {'+'.join(intervals)}", flush=True)
    if not symbols:
        return 1

    failed: list[str] = []
    for interval in intervals:
        for symbol in symbols:
            try:
                marketlib.run_with_retry(fetch_symbol, symbol, interval)
            except Exception as exc:  # noqa: BLE001 - 单只失败不中断整体
                print(f"  [失败] {symbol} {interval}: {exc}", flush=True)
                failed.append(f"{symbol}@{interval}")
            time.sleep(config.REQUEST_DELAY)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取纳指100分钟级K线")
    parser.add_argument(
        "--interval",
        choices=["1m", "15m", "both"],
        default="both",
        help="K线周期（默认 both）",
    )
    args = parser.parse_args()
    intervals = ["1m", "15m"] if args.interval == "both" else [args.interval]
    return run(intervals)


if __name__ == "__main__":
    sys.exit(main())