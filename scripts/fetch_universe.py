"""美股全市场股票列表拉取脚本。

从公开的全市场股票代码清单下载全部美股代码，写入 universe 目录：
data/universe/us.csv

数据源：
  https://raw.githubusercontent.com/abbadata/stock-tickers/main/data/allsymbols.txt

用法：
    python scripts/fetch_universe.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

# 全市场美股代码清单（每行一个符号）
UNIVERSE_URL = (
    "https://raw.githubusercontent.com/abbadata/stock-tickers/main/data/allsymbols.txt"
)


def download(url: str) -> str:
    """下载文件并解码为文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_symbols(text: str) -> set[str]:
    """解析每行一个符号的清单，去空行、去重。"""
    symbols: set[str] = set()
    for line in text.splitlines():
        code = line.strip()
        if code:
            symbols.add(code)
    return symbols


def run() -> int:
    try:
        print("下载全市场美股列表...", flush=True)
        text = download(UNIVERSE_URL)

        symbols = parse_symbols(text)
        if not symbols:
            print("未解析出任何股票代码，中止", file=sys.stderr)
            return 1

        out = ROOT / config.DATA_DIR / config.UNIVERSE_SUBDIR / config.UNIVERSE_FILE
        out.parent.mkdir(parents=True, exist_ok=True)
        # 排序后写入，保证分批结果稳定
        rows = sorted(symbols)
        out.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"  共 {len(rows)} 只美股 -> {out.relative_to(ROOT)}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"拉取美股列表失败: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())