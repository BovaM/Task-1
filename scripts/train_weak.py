"""Заведомо слабый champion - модель только по gpa.

Один признак gpa почти не разделяет классы (PR-AUC ~0.85 при доле класса 0.84),
поэтому следующий запуск DAG с полным набором признаков гарантированно проходит гейт.
Намеренно слабый champion — задокументировано в REPORT.md.

MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run python scripts/train_weak.py
"""
import json
import os

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from roi_service.config import settings
from roi_service.train import DATA_PATH, MODEL_NAME, SEED, SKOPS_TRUSTED, TARGET, load_and_validate

FEATURES = ["gpa"]


def main() -> dict:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_registry_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "roi"))
    df = load_and_validate(DATA_PATH)

    x_train, x_test, y_train, y_test = train_test_split(
        df[FEATURES], df[TARGET], test_size=0.2, stratify=df[TARGET], random_state=SEED,
    )
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000)),
    ]).fit(x_train, y_train)

    pr_auc = float(average_precision_score(y_test, pipeline.predict_proba(x_test)[:, 1]))

    client = MlflowClient()
    with mlflow.start_run(run_name="weak champion (gpa only)"):
        mlflow.log_params({"features": FEATURES, "seed": SEED, "note": "намеренно слабый champion для сценария 1"})
        mlflow.log_metric("pr_auc", pr_auc)
        mlflow.log_dict({"features": FEATURES, "threshold": 0.5}, "metadata.json")
        info = mlflow.sklearn.log_model(pipeline, name="model", registered_model_name=MODEL_NAME,
                                        skops_trusted_types=SKOPS_TRUSTED)
        version = info.registered_model_version

    try:
        client.get_model_version_by_alias(MODEL_NAME, "champion")
    except MlflowException:
        pass
    client.set_registered_model_alias(MODEL_NAME, "challenger", version)
    client.set_registered_model_alias(MODEL_NAME, "champion", version)

    result = {"run_id": info.run_id, "version": version, "pr_auc": round(pr_auc, 4),
              "champion_before": None, "champion_pr_auc_before": None, "promoted": True}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
