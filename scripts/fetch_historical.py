"""历史数据拉取脚本。

从 Yahoo Finance 拉取日线数据，每只股票写入一个 CSV 文件，按区域分目录存放：
    data/{region}/kline/{symbol}.csv

默认增量模式：若文件已存在，只拉取其最后日期之后的新数据，与已有数据
合并并按日期去重（追加而非全量重拉），避免每天重复下载全部历史。
首次运行或使用 --full 时拉取近 config.HISTORY_PERIOD 的全量历史。

用法：
    python scripts/fetch_historical.py                  # 增量拉取全部区域
    python scripts/fetch_historical.py --region us      # 仅处理指定区域
    python scripts/fetch_historical.py --full           # 强制全量刷新
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# 允许从项目根目录导入 config
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import marketlib  # noqa: E402

# 写入 CSV 时展示的字段名（与 yfinance 返回一致）
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
# 增量拉取时的回看缓冲天数：覆盖数据修订（除权/分红导致 Adj Close 变化）
INCREMENTAL_BUFFER_DAYS = 7


def output_path(region: str, symbol: str) -> Path:
    return ROOT / config.DATA_DIR / region / config.KLINE_SUBDIR / f"{symbol}.csv"


def fetch_symbol(region: str, symbol: str, full: bool = False) -> Path | None:
    """拉取单只股票历史数据并写盘，返回输出路径；失败返回 None。"""
    out = output_path(region, symbol)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    existing = marketlib.read_kline(out)

    if full or existing is None or existing.empty:
        # 全量模式 / 无现有文件：拉取全部历史
        df = ticker.history(
            period=config.HISTORY_PERIOD,
            interval=config.INTERVAL,
            auto_adjust=False,
        )
        mode_label = "全量"
    else:
        # 增量模式：只拉取最后日期之前的缓冲段（含回看，覆盖修订）
        last_date = existing.index.max()
        start = (last_date - pd.Timedelta(days=INCREMENTAL_BUFFER_DAYS)).date()
        df = ticker.history(
            start=str(start),
            interval=config.INTERVAL,
            auto_adjust=False,
        )
        mode_label = "增量"

    if df is None or df.empty:
        print(f"  [跳过] {symbol}: 无数据返回", flush=True)
        return out if out.exists() else None

    # 保留核心列（仅取实际存在的列），索引为日期
    cols = [c for c in COLS if c in df.columns]
    merged = marketlib.merge_kline(out, df, cols)
    print(
        f"  [{mode_label}] {symbol} -> {out.relative_to(ROOT)} (共 {len(merged)} 行)",
        flush=True,
    )
    return out


def run(
    region: str | None,
    full: bool,
    index: str | None = None,
    batch: int = 0,
    batches: int = 1,
) -> int:
    targets: list[tuple[str, str]] = []
    if index:
        reg, syms = marketlib.load_index_symbols(index)
        syms = marketlib.slice_batch(syms, batch, batches)
        targets = [(reg, s) for s in syms]
    elif region:
        reg = region
        syms = marketlib.load_symbols(reg)
        syms = marketlib.slice_batch(syms, batch, batches)
        targets = [(reg, s) for s in syms]
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
        try:
            marketlib.run_with_retry(fetch_symbol, reg, symbol, full)
        except Exception as exc:  # noqa: BLE001 - 单只失败不中断整体
            print(f"  [失败] {reg} {symbol}: {exc}", flush=True)
            failed.append(f"{reg}:{symbol}")
        # 控制请求频率，避免触发 Yahoo 限流
        time.sleep(config.REQUEST_DELAY)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取历史日线数据")
    parser.add_argument(
        "--region",
        choices=list(config.REGIONS),
        help="仅处理指定区域",
    )
    parser.add_argument(
        "--index",
        choices=sorted(config.INDEX_CONFIG),
        help="仅处理指定指数成分股（csi300/csi500/ndx100/sp500/hsi）",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="强制全量刷新（默认增量追加）",
    )
    parser.add_argument("--batch", type=int, default=0, help="当前批次（0 起）")
    parser.add_argument("--batches", type=int, default=1, help="总批次数")
    args = parser.parse_args()
    return run(args.region, args.full, args.index, args.batch, args.batches)


if __name__ == "__main__":
    sys.exit(main())