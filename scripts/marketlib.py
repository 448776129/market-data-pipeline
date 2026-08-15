"""共享工具：解析区域股票列表、支持全市场模式与分批切片。

三个 fetch 脚本共用此模块以避免重复逻辑。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


def read_kline(path: Path) -> pd.DataFrame | None:
    """读取已有 K 线 CSV（索引为日期），文件不存在时返回 None。"""
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    df.index = df.index.normalize()
    return df


def merge_kline(path: Path, fresh: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """将 fresh 数据与 path 处的已有 CSV 合并、按日期去重后写回。

    返回合并后的 DataFrame。若已有文件存在，仅追加/覆盖缺失与更新的日期；
    否则直接写入 fresh。
    """
    fresh = fresh[cols].copy()
    fresh.index = fresh.index.tz_localize(None) if fresh.index.tz is not None else fresh.index
    fresh.index = fresh.index.normalize()

    existing = read_kline(path)
    if existing is None or existing.empty:
        merged = fresh
    else:
        merged = pd.concat([existing, fresh])
        # 按日期去重，保留最新一行
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    path.parent.mkdir(parents=True, exist_ok=True)
    merged.index.name = "Date"
    merged.to_csv(path, encoding="utf-8")
    return merged


def load_symbols(region: str) -> list[str]:
    """返回指定区域的股票代码列表。

    若 config.REGIONS[region] 为空（全市场模式），则从 universe 文件读取。
    否则返回硬编码列表。找不到则返回空列表。
    """
    hardcoded = config.REGIONS.get(region, [])
    if hardcoded:
        return list(hardcoded)

    # 全市场模式：从 data/universe/{region}.csv 读取
    universe_file = config.UNIVERSE_FILES.get(region)
    if not universe_file:
        return []
    path = ROOT / config.DATA_DIR / config.UNIVERSE_SUBDIR / universe_file
    if not path.exists():
        print(f"  [警告] universe 文件不存在: {path.relative_to(ROOT)}", file=sys.stderr)
        return []
    symbols = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return symbols


def slice_batch(symbols: list[str], batch: int, batches: int) -> list[str]:
    """将符号列表按顺序切成 batches 批，返回第 batch 批（0 起）。

    batch 越界时返回空列表。
    """
    if batches <= 1 or batch < 0 or batch >= batches:
        if batch == 0 and batches <= 1:
            return symbols
        return []
    n = len(symbols)
    size = (n + batches - 1) // batches  # 向上取整
    start = batch * size
    return symbols[start : start + size]


def run_with_retry(fn, *args, retries: int | None = None, delay: float | None = None, **kwargs):
    """执行 fn，遇瞬时错误按指数退避重试；重试耗尽后抛出原异常。"""
    retries = config.MAX_RETRIES if retries is None else retries
    delay = config.REQUEST_DELAY if delay is None else delay
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 记录并重试
            last_exc = exc
            if attempt < retries - 1:
                wait = delay * (2**attempt)
                print(f"    重试 {attempt+1}/{retries-1}（等 {wait:.0f}s）：{exc}", flush=True)
                time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    return None