"""非K线数据拉取脚本。

从 Yahoo Finance 拉取除 K 线以外的数据（行情快照 info、财务、分析师、
分红拆股等），每只股票写入一个 JSON 文件，按区域分目录存放：
data/{region}/meta/{symbol}.json

没有数据的字段留空（null）。与 K 线数据（data/{region}/kline/）分开存放。

用法：
    python scripts/fetch_meta.py                # 处理全部区域
    python scripts/fetch_meta.py --region kr    # 仅处理指定区域
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import marketlib  # noqa: E402


def output_path(region: str, symbol: str) -> Path:
    return ROOT / config.DATA_DIR / region / config.META_SUBDIR / f"{symbol}.json"


def clean(value):
    """递归清洗 NaN/inf，使其可被 JSON 序列化；其余原样返回。"""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def df_to_records(obj, limit: int | None = None) -> list | None:
    """DataFrame/Series 转成记录列表；空则返回 None。"""
    if obj is None or getattr(obj, "empty", True):
        return None
    out: list = []
    if hasattr(obj, "iterrows"):  # DataFrame
        for idx, row in obj.iterrows():
            rec: dict = {"index": str(idx)}
            for col, val in row.items():
                rec[str(col)] = clean(val)
            out.append(rec)
            if limit and len(out) >= limit:
                break
    else:  # Series
        for idx, val in obj.items():
            out.append({"index": str(idx), "value": clean(val)})
            if limit and len(out) >= limit:
                break
    return out or None


def safe_get(ticker, attr, *args, **kwargs):
    """安全获取 ticker 属性；异常或无值返回 None。"""
    try:
        val = getattr(ticker, attr)
        if callable(val):
            val = val(*args, **kwargs)
        if val is None:
            return None
        # 空 DataFrame / 空 Series 视为无数据
        if hasattr(val, "empty") and not hasattr(val, "shape"):
            if val.empty:
                return None
        elif hasattr(val, "shape") and val.shape == (0,):
            return None
        return val
    except Exception:  # noqa: BLE001 - 单字段失败不影响整体
        return None


# info 中值得保留的关键字段（其余丢弃以控制体积）
INFO_KEEP = [
    "longName", "shortName", "sector", "industry", "country", "exchange",
    "currency", "marketCap", "currentPrice", "open", "previousClose", "dayHigh",
    "dayLow", "regularMarketPrice", "regularMarketPreviousClose", "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow", "trailingPE", "forwardPE", "priceToBook", "dividendYield",
    "dividendRate", "trailingEps", "forwardEps", "beta", "volume", "averageVolume",
    "sharesOutstanding", "floatShares", "targetMeanPrice", "targetHighPrice",
    "targetLowPrice", "recommendationKey", "totalRevenue", "grossProfits",
    "freeCashflow", "totalDebt", "totalCash", "profitMargins", "returnOnEquity",
    "returnOnAssets", "earningsGrowth", "revenueGrowth",
]


def fetch_symbol(region: str, symbol: str) -> Path | None:
    ticker = yf.Ticker(symbol)

    info = safe_get(ticker, "info")
    info_slim = (
        {k: clean(info.get(k)) for k in INFO_KEEP if k in info}
        if isinstance(info, dict)
        else None
    )

    data = {
        "symbol": symbol,
        "region": region,
        "name": info.get("longName") if isinstance(info, dict) else None,
        "currency": info.get("currency") if isinstance(info, dict) else None,
        "exchange": info.get("exchange") if isinstance(info, dict) else None,
        "isin": clean(safe_get(ticker, "isin")),
        # 行情快照
        "info": info_slim,
        # 分红 / 拆股 / 资本利得
        "dividends": df_to_records(safe_get(ticker, "dividends")),
        "splits": df_to_records(safe_get(ticker, "splits")),
        "capital_gains": df_to_records(safe_get(ticker, "capital_gains")),
        # 财务（年度 + 季度摘要）
        "financials": df_to_records(safe_get(ticker, "financials")),
        "balancesheet": df_to_records(safe_get(ticker, "balance_sheet")),
        "cashflow": df_to_records(safe_get(ticker, "cashflow")),
        "quarterly_financials": df_to_records(safe_get(ticker, "quarterly_financials")),
        # 分析师与评级
        "analyst_price_targets": clean(safe_get(ticker, "analyst_price_targets")),
        "recommendations_summary": df_to_records(
            safe_get(ticker, "recommendations_summary")
        ),
        "earnings_dates": df_to_records(safe_get(ticker, "earnings_dates")),
        # 大股东 / 机构持股
        "major_holders": df_to_records(safe_get(ticker, "major_holders")),
        "institutional_holders": df_to_records(
            safe_get(ticker, "institutional_holders")
        ),
    }

    out = output_path(region, symbol)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)

    print(f"  [完成] {symbol} -> {out.relative_to(ROOT)}", flush=True)
    return out


def run(region: str | None, batch: int = 0, batches: int = 1) -> int:
    regions = [region] if region else list(config.REGIONS)
    failed: list[str] = []

    for reg in regions:
        symbols = marketlib.load_symbols(reg)
        symbols = marketlib.slice_batch(symbols, batch, batches)
        print(
            f"[区域] {reg} ({len(symbols)} 只"
            + (f", 批 {batch+1}/{batches}" if batches > 1 else "")
            + ")",
            flush=True,
        )
        for symbol in symbols:
            try:
                fetch_symbol(reg, symbol)
            except Exception as exc:  # noqa: BLE001
                print(f"  [失败] {symbol}: {exc}", flush=True)
                failed.append(symbol)
            time.sleep(1)

    if failed:
        print(f"失败 {len(failed)} 只: {failed}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取非K线数据")
    parser.add_argument("--region", choices=config.REGIONS, help="仅处理指定区域")
    parser.add_argument("--batch", type=int, default=0, help="当前批次（0 起）")
    parser.add_argument("--batches", type=int, default=1, help="总批次数")
    args = parser.parse_args()
    return run(args.region, args.batch, args.batches)


if __name__ == "__main__":
    sys.exit(main())