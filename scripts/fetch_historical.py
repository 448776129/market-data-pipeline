"""历史数据拉取脚本。

从 Yahoo Finance 拉取近 5 年日线数据，每只股票写入一个 CSV 文件，
按区域分目录存放：data/{region}/{symbol}.csv

用法：
    python scripts/fetch_historical.py            # 拉取全部区域
    python scripts/fetch_historical.py --region us   # 仅拉取指定区域
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yfinance as yf

# 允许从项目根目录导入 config
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

# 写入 CSV 时展示的字段名（与 yfinance 返回一致）
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def output_path(region: str, symbol: str) -> Path:
    return ROOT / config.DATA_DIR / region / f"{symbol}.csv"


def fetch_symbol(region: str, symbol: str) -> Path | None:
    """拉取单只股票历史数据并写盘，返回输出路径；失败返回 None。"""
    out = output_path(region, symbol)
    out.parent.mkdir(parents=True, exist_ok=True)

    ticker = yf.Ticker(symbol)
    # auto_adjust=False 保证返回包含 Adj Close 的原始列
    df = ticker.history(
        period=config.HISTORY_PERIOD,
        interval=config.INTERVAL,
        auto_adjust=False,
    )

    if df is None or df.empty:
        print(f"  [跳过] {symbol}: 无数据返回", flush=True)
        return None

    # 保留核心列（仅取实际存在的列），索引为日期
    cols = [c for c in COLS if c in df.columns]
    df = df[cols].copy()
    df.index.name = "Date"
    # 日期归一化为 YYYY-MM-DD，避免时区漂移导致的重复行
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df.index = df.index.normalize()
    df.to_csv(out, encoding="utf-8")
    print(f"  [完成] {symbol} -> {out.relative_to(ROOT)} ({len(df)} 行)", flush=True)
    return out


def run(region: str | None) -> int:
    regions = [region] if region else list(config.REGIONS)
    failed: list[str] = []

    for reg in regions:
        symbols = config.REGIONS.get(reg, [])
        print(f"[区域] {reg} ({len(symbols)} 只)", flush=True)
        for symbol in symbols:
            try:
                fetch_symbol(reg, symbol)
            except Exception as exc:  # noqa: BLE001 - 单只失败不中断整体
                print(f"  [失败] {symbol}: {exc}", flush=True)
                failed.append(symbol)
            # 控制请求频率，避免触发 Yahoo 限流
            time.sleep(1)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取历史日线数据")
    parser.add_argument("--region", choices=config.REGIONS, help="仅处理指定区域")
    args = parser.parse_args()
    return run(args.region)


if __name__ == "__main__":
    sys.exit(main())