"""Анализ датасета (describe, доля класса, корреляции с целью)"""
import pandas as pd

df = pd.read_csv("data/college_major_roi.csv")
print("shape:", df.shape)
print("\n=== dtypes ===")
print(df.dtypes)
print("\n=== describe ===")
print(df.describe().T.to_string())
print("\n=== пропуски ===")
print(df.isna().sum().to_string())
print("\n=== positive_roi share ===", df["positive_roi"].mean())
print("\n=== unique категории ===")
for c in ["major", "major_category", "institution_tier", "region"]:
    print(c, "n=", df[c].nunique(), sorted(df[c].dropna().unique())[:30])
print("\n=== корреляция признаков с positive_roi ===")
num = df.select_dtypes("number").columns.tolist()
print(df[num].corrwith(df["positive_roi"]).sort_values(ascending=False).to_string())
