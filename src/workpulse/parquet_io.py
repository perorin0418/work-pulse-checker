from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_or_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def append_row(path: Path, row: dict, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = read_or_empty(path, columns)
    new_row = pd.DataFrame([row], columns=columns)
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_parquet(path, index=False)
