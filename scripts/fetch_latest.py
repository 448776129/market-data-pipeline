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

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
# 补拉天数：覆盖周末/节假日，保证当日数据不缺
RECENT_DAYS = "5d"


def output_path(region: str, symbol: str) -> Path:
    return ROOT / config.DATA_DIR / region / f"{symbol}.csv"


def load_existing(region: str, symbol: str) -> pd.DataFrame | None:
    out = output_path(region, symbol)
    if not out.exists():
        return None
    df = pd.read_csv(out, index_col="Date", parse_dates=True)
    df.index = df.index.normalize()
    return df


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

    # 保留核心列（仅取实际存在的列），索引为日期
    cols = [c for c in COLS if c in fresh.columns]
    fresh = fresh[cols].copy()
    fresh.index = fresh.index.tz_localize(None) if fresh.index.tz is not None else fresh.index
    fresh.index = fresh.index.normalize()

    existing = load_existing(region, symbol)
    if existing is None:
        # 无历史文件（如首次运行），退化为拉取全量历史
        merged = fresh
        print(f"  [警告] {symbol}: 无现有文件，仅写入最近数据", flush=True)
    else:
        merged = pd.concat([existing, fresh])
        # 按日期去重，保留最新一行
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    merged.to_csv(out, encoding="utf-8")
    print(f"  [更新] {symbol} -> {out.relative_to(ROOT)} (共 {len(merged)} 行)", flush=True)
    return out


def run(region: str | None, symbol: str | None) -> int:
    targets: list[tuple[str, str]] = []
    if symbol:
        # 按符号反查区域
        for reg, syms in config.REGIONS.items():
            if symbol in syms:
                targets.append((reg, symbol))
    elif region:
        targets.extend((region, s) for s in config.REGIONS.get(region, []))
    else:
        targets = [(reg, s) for reg, syms in config.REGIONS.items() for s in syms]

    if not targets:
        print("未找到匹配的符号/区域", file=sys.stderr)
        return 1

    failed: list[str] = []
    for reg, sym in targets:
        try:
            fetch_symbol(reg, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"  [失败] {sym}: {exc}", flush=True)
            failed.append(sym)
        time.sleep(1)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="当日数据增量更新")
    parser.add_argument("--region", choices=config.REGIONS, help="仅处理指定区域")
    parser.add_argument("--symbol", help="仅处理指定符号")
    args = parser.parse_args()
    return run(args.region, args.symbol)


if __name__ == "__main__":
    sys.exit(main())