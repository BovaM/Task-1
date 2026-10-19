"""Испорченная выгрузка для сценария 3: net_cost_usd тихо перешёл из долларов в центы.

  uv run python scripts/break_export.py
Файл читается, типы те же, строк столько же. Вернуть: git revert, затем uv run dvc checkout --force
"""
from pathlib import Path

import pandas as pd

PATH = Path("data/college_major_roi.csv")
df = pd.read_csv(PATH)
df["net_cost_usd"] = df["net_cost_usd"] * 100
df.to_csv(PATH, index=False)
print(f"{PATH}: net_cost_usd в центах, медиана {df['net_cost_usd'].median():.0f}, строк {len(df)}")
