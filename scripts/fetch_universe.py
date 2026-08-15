"""全市场股票列表拉取脚本。

从公开数据源拉取各市场的全部股票代码，写入 universe 目录：
data/universe/{region}.csv

支持的市场：
  - us: 每行一个美股代码
  - hk: 港股代码清单（code 列），加 .HK 后缀
  - kr: KRX 官方缓存（动态日期），Code 列加 .KS 后缀，过滤 KONEX

A股（cn）代码由仓库内置清单提供，不在此拉取。

用法：
    python scripts/fetch_universe.py [--region us|hk|kr|cn]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

# KRX 接口：获取最近交易日，用于定位缓存文件
KRX_MAXDT_URL = (
    "http://data.krx.co.kr/comm/bldAttendant/executeForResourceBundle.cmd"
    "?baseName=krx.mdc.i18n.component&key=B128.bld"
)
KRX_CACHE_URL = (
    "https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
    "master/data/listing/krx/{date}.csv"
)
# 韩股过滤：排除 KONEX（MarketId == KNX）
KRX_EXCLUDE_MARKET = "KNX"


def download(url: str) -> str:
    """下载文件并解码为文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_us() -> set[str]:
    """美股：每行一个代码。"""
    text = download(config.UNIVERSE_SOURCES["us"])
    return {line.strip() for line in text.splitlines() if line.strip()}


def fetch_hk() -> set[str]:
    """港股：从 CSV 取 code 列，加 .HK。"""
    text = download(config.UNIVERSE_SOURCES["hk"])
    reader = csv.DictReader(io.StringIO(text))
    symbols: set[str] = set()
    for row in reader:
        code = (row.get("code") or "").strip()
        if code:
            symbols.add(f"{code}.HK")
    return symbols


def fetch_kr() -> set[str]:
    """韩股：查询最近交易日，从 KRX 缓存取 Code 列，加 .KS，过滤 KONEX。"""
    # 1. 获取最近交易日
    maxdt_raw = download(KRX_MAXDT_URL)
    try:
        date_str = json.loads(maxdt_raw)["result"]["output"][0]["max_work_dt"]
        date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"获取KRX最近交易日失败: {exc}") from exc

    # 2. 下载当日缓存
    text = download(KRX_CACHE_URL.format(date=date))
    reader = csv.DictReader(io.StringIO(text))
    symbols: set[str] = set()
    for row in reader:
        market_id = (row.get("MarketId") or "").strip()
        if market_id == KRX_EXCLUDE_MARKET:
            continue
        code = (row.get("Code") or "").strip()
        if code:
            symbols.add(f"{code}.KS")
    return symbols


FETCHERS = {
    "us": fetch_us,
    "hk": fetch_hk,
    "kr": fetch_kr,
}


def run(region: str | None) -> int:
    regions = [region] if region else list(FETCHERS)
    failed = False
    for reg in regions:
        fetcher = FETCHERS.get(reg)
        if not fetcher:
            print(f"  [跳过] {reg}: 无动态数据源（cn 由仓库内置清单提供）", flush=True)
            continue
        try:
            print(f"下载 {reg} 全市场列表...", flush=True)
            symbols = fetcher()
            if not symbols:
                print(f"  未解析出任何股票代码，跳过 {reg}", file=sys.stderr)
                failed = True
                continue
            out = ROOT / config.DATA_DIR / config.UNIVERSE_SUBDIR / config.UNIVERSE_FILES[reg]
            out.parent.mkdir(parents=True, exist_ok=True)
            rows = sorted(symbols)
            out.write_text("\n".join(rows) + "\n", encoding="utf-8")
            print(f"  共 {len(rows)} 只 -> {out.relative_to(ROOT)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  [失败] {reg}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取全市场股票列表")
    parser.add_argument("--region", choices=list(FETCHERS) + ["cn"], help="仅处理指定区域")
    args = parser.parse_args()
    return run(args.region)


if __name__ == "__main__":
    sys.exit(main())