"""выбросы pctile, уникальность id, шум PR-AUC по seed'ам на 7 безопасных признаках"""
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")
df = pd.read_csv("data/college_major_roi.csv")

print("pctile>100 rows:", (df["institution_selectivity_pctile"] > 100).sum())
print("pctile==102 rows:", (df["institution_selectivity_pctile"] == 102).sum())
print("pctile max:", df["institution_selectivity_pctile"].max())
print("grad_id unique:", df["grad_id"].nunique(), "of", len(df))
print("gpa NaN:", df["gpa"].isna().sum(), " net_cost NaN:", df["net_cost_usd"].isna().sum())
print("net_cost median:", df["net_cost_usd"].median(), " min:", df["net_cost_usd"].min(), " max:", df["net_cost_usd"].max())

NUMERIC = ["institution_selectivity_pctile", "had_internship", "gpa", "net_cost_usd"]
CATEGORICAL = ["major", "institution_tier", "region"]
TARGET = "positive_roi"


def pipeline(c: float) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUMERIC),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("ohe", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
    ])
    return Pipeline([("pre", pre), ("model", LogisticRegression(max_iter=1000, C=c))])


scores = []
for seed in range(10):
    x_tr, x_te, y_tr, y_te = train_test_split(df[NUMERIC + CATEGORICAL], df[TARGET], test_size=0.2,
                                              stratify=df[TARGET], random_state=seed)
    p = pipeline(1.0).fit(x_tr, y_tr)
    pr = average_precision_score(y_te, p.predict_proba(x_te)[:, 1])
    scores.append(pr)
    print(f"seed {seed}: pr_auc={pr:.4f}")

s = np.array(scores)
print(f"\nmean={s.mean():.4f}  std={s.std():.4f}  min={s.min():.4f}  max={s.max():.4f}")
print(f"3*std={3*s.std():.4f}  разброс max-min={s.max()-s.min():.4f}")
