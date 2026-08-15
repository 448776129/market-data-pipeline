"""分钟级K线数据拉取脚本。

从 Yahoo Finance 拉取分钟级K线（1分钟、15分钟、1小时），每只股票、每个周期
各写入一个 CSV 文件，按区域与周期分目录存放：
    data/{region}/kline_1m/{symbol}.csv
    data/{region}/kline_15m/{symbol}.csv
    data/{region}/kline_1h/{symbol}.csv

范围：
    - 默认按区域拉取全市场（US/HK/CN/KR），支持分批（--batch/--batches）
    - 也可用 --universe sp500|ndx100 拉取指定指数成分股（仅美股）

增量查重：与已有文件按时间点合并去重（追加而非覆盖），重复运行只补新增时间点。

用法：
    python scripts/fetch_intraday.py                          # 全部区域全市场
    python scripts/fetch_intraday.py --region us              # 仅美股全市场
    python scripts/fetch_intraday.py --region us --universe sp500  # 仅标普500
    python scripts/fetch_intraday.py --region us --batch 0 --batches 20
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
INDEX_COL = "Datetime"

# 周期 -> 子目录名
SUBDIR = {
    "1m": config.INTRADAY_M1_SUBDIR,
    "15m": config.INTRADAY_M15_SUBDIR,
    "1h": config.INTRADAY_M1H_SUBDIR,
}

# universe 名 -> 清单文件名（仅美股）
UNIVERSE_FILES = {
    "sp500": config.SP500_FILE,
    "ndx100": config.NASDAQ100_FILE,
}


def load_universe_symbols(universe: str) -> list[str]:
    """读取指定指数成分股清单。"""
    fname = UNIVERSE_FILES.get(universe)
    if not fname:
        print(f"  [警告] 未知指数: {universe}", file=sys.stderr)
        return []
    path = ROOT / config.DATA_DIR / config.UNIVERSE_SUBDIR / fname
    if not path.exists():
        print(f"  [警告] 成分股清单不存在: {path.relative_to(ROOT)}", file=sys.stderr)
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def output_path(region: str, symbol: str, interval: str) -> Path:
    return ROOT / config.DATA_DIR / region / SUBDIR[interval] / f"{symbol}.csv"


def fetch_symbol(region: str, symbol: str, interval: str) -> Path | None:
    """拉取单只股票指定周期的分钟K线，追加去重后返回输出路径；失败返回 None。"""
    out = output_path(region, symbol, interval)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    df = ticker.history(
        period=config.INTRADAY_PERIOD[interval],
        interval=interval,
        auto_adjust=False,
    )

    if df is None or df.empty:
        print(f"  [跳过] {symbol} {interval}: 无数据返回", flush=True)
        return out if out.exists() else None

    cols = [c for c in COLS if c in df.columns]
    merged = marketlib.merge_kline(out, df, cols, index_col=INDEX_COL)
    print(
        f"  [更新] {symbol} {interval} -> {out.relative_to(ROOT)} (共 {len(merged)} 行)",
        flush=True,
    )
    return out


def run(
    region: str | None,
    intervals: list[str],
    universe: str | None = None,
    batch: int = 0,
    batches: int = 1,
) -> int:
    regions: list[str]
    if universe:
        # 指数成分股模式（仅美股）
        regions = ["us"]
        syms_map = {"us": load_universe_symbols(universe)}
    elif region:
        regions = [region]
        syms_map = {region: marketlib.load_symbols(region)}
    else:
        regions = list(config.REGIONS)
        syms_map = {reg: marketlib.load_symbols(reg) for reg in regions}

    failed: list[str] = []
    for reg in regions:
        symbols = marketlib.slice_batch(syms_map[reg], batch, batches)
        print(
            f"[区域] {reg} ({len(symbols)} 只"
            + (f", 批 {batch+1}/{batches}" if batches > 1 else "")
            + f", 周期 {'+'.join(intervals)})",
            flush=True,
        )
        for interval in intervals:
            for symbol in symbols:
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
    parser = argparse.ArgumentParser(description="拉取分钟级K线")
    parser.add_argument(
        "--region",
        choices=list(config.REGIONS),
        help="仅处理指定区域（默认全部）",
    )
    parser.add_argument(
        "--universe",
        choices=list(UNIVERSE_FILES),
        help="拉取指定指数成分股（仅美股，sp500/ndx100）",
    )
    parser.add_argument(
        "--interval",
        choices=["1m", "15m", "1h", "all"],
        default="all",
        help="K线周期（默认 all）",
    )
    parser.add_argument("--batch", type=int, default=0, help="当前批次（0 起）")
    parser.add_argument("--batches", type=int, default=1, help="总批次数")
    args = parser.parse_args()
    intervals = ["1m", "15m", "1h"] if args.interval == "all" else [args.interval]
    return run(args.region, intervals, args.universe, args.batch, args.batches)


if __name__ == "__main__":
    sys.exit(main())