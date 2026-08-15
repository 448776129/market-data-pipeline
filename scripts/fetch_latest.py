"""当日数据增量脚本。

拉取最新的当日（含最近几日补缺）数据，与已有 CSV 合并、按日期去重后写回，
用于在历史数据基础上做每日增量更新。每只股票仍是一个文件。

用法：
    python scripts/fetch_latest.py                 # 处理全部区域
    python scripts/fetch_latest.py --region us     # 仅处理指定区域
    python scripts/fetch_latest.py --symbol TSLA   # 仅处理指定符号
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
# 补拉天数：覆盖周末/节假日，保证当日数据不缺
RECENT_DAYS = "5d"


def output_path(region: str, symbol: str) -> Path:
    return ROOT / config.DATA_DIR / region / config.KLINE_SUBDIR / f"{symbol}.csv"


def fetch_symbol(region: str, symbol: str) -> Path | None:
    out = output_path(region, symbol)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    # auto_adjust=False 保证返回包含 Adj Close 的原始列
    fresh = ticker.history(
        period=RECENT_DAYS,
        interval=config.INTERVAL,
        auto_adjust=False,
    )

    if fresh is None or fresh.empty:
        print(f"  [跳过] {symbol}: 无最新数据", flush=True)
        return out if out.exists() else None

    # 保留核心列（仅取实际存在的列）
    cols = [c for c in COLS if c in fresh.columns]
    merged = marketlib.merge_kline(out, fresh, cols)
    print(f"  [更新] {symbol} -> {out.relative_to(ROOT)} (共 {len(merged)} 行)", flush=True)
    return out


def run(region: str | None, symbol: str | None, batch: int = 0, batches: int = 1) -> int:
    targets: list[tuple[str, str]] = []
    if symbol:
        # 按符号反查区域
        for reg, syms in config.REGIONS.items():
            if symbol in syms:
                targets.append((reg, symbol))
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
        print("未找到匹配的符号/区域", file=sys.stderr)
        return 1

    failed: list[str] = []
    for reg, sym in targets:
        try:
            marketlib.run_with_retry(fetch_symbol, reg, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"  [失败] {sym}: {exc}", flush=True)
            failed.append(sym)
        time.sleep(config.REQUEST_DELAY)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="当日数据增量更新")
    parser.add_argument("--region", choices=config.REGIONS, help="仅处理指定区域")
    parser.add_argument("--symbol", help="仅处理指定符号")
    parser.add_argument("--batch", type=int, default=0, help="当前批次（0 起）")
    parser.add_argument("--batches", type=int, default=1, help="总批次数")
    args = parser.parse_args()
    return run(args.region, args.symbol, args.batch, args.batches)


if __name__ == "__main__":
    sys.exit(main())