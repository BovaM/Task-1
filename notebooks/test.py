import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "data" / "college_major_roi.csv")

categorical = ["major", "institution_tier", "region"]
numerical = ["institution_selectivity_pctile", "gpa", "net_cost_usd", "had_internship"]
features = categorical + numerical
target = "positive_roi"

print(df[features].isna().sum())
print(df[numerical].describe())  # по этому выводу проверьте границы в schemas.py

X_tr, X_te, y_tr, y_te = train_test_split(
    df[features], df[target], test_size=0.2, stratify=df[target], random_state=42
)
pre = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), numerical),
])
pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000))])
pipe.fit(X_tr, y_tr)
print("AUC", roc_auc_score(y_te, pipe.predict_proba(X_te)[:, 1]))

metadata = {"model_version": "1.0.0", "features": features, "threshold": 0.5, "target": target}
out = ROOT / "artifacts"
out.mkdir(parents=True, exist_ok=True)
joblib.dump({"pipeline": pipe, "metadata": metadata}, out / "model.joblib")

sample = json.loads(df[features].iloc[[0]].to_json(orient="records"))[0]
(ROOT / "good.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2))
print("sample:", sample)