"""Обучение модели оттока: проверка данных, обучение, запись в MLflow, регистрация и гейт.

  MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run python -m roi.train

Новая версия всегда получает алиас challenger. Алиас champion она получает, только если
ROC-AUC на отложенной выборке лучше, чем у текущего champion (или champion ещё нет).
"""
import hashlib
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA_PATH = Path(os.getenv("DATA_PATH", "data/college_major_roi.csv"))
MODEL_NAME = os.getenv("MODEL_NAME", "roi")
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "roi")

C = float(os.getenv("C", "1.0"))
MIN_GAIN = float(os.getenv("GATE_MIN_GAIN", "0.0"))

SEED = 42

SKOPS_TRUSTED = [
    "numpy.dtype",
    "sklearn.compose._column_transformer._RemainderColsList",
]


NUMERIC = [
    "institution_selectivity_pctile",
    "gpa",
    "had_internship",
    "completed_on_time",
    "net_cost_usd",
    "debt_usd",
    "hs_baseline_10yr_usd",
]

CATEGORICAL = [
    "major",
    "major_category",
    "institution_tier",
    "region",
]

TARGET = "positive_roi"


def load_and_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    missing = set(NUMERIC + CATEGORICAL + [TARGET]) - set(df.columns)

    if missing:
        raise ValueError(f"в данных нет колонок: {sorted(missing)}")

    return df


def build_pipeline(c: float) -> Pipeline:
    preprocess = ColumnTransformer([
        (
            "num",
            Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]),
            NUMERIC,
        ),
        (
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]),
            CATEGORICAL,
        ),
    ])

    return Pipeline([
        ("preprocess", preprocess),
        ("model", LogisticRegression(max_iter=1000, C=c)),
    ])


def champion_score(
    client: MlflowClient,
) -> tuple[str | None, float | None]:

    try:
        version = client.get_model_version_by_alias(
            MODEL_NAME,
            "champion",
        )
    except MlflowException:
        return None, None

    score = client.get_run(
        version.run_id
    ).data.metrics.get("pr_auc")

    return version.version, score


def main() -> dict:
    df = load_and_validate(DATA_PATH)

    features = NUMERIC + CATEGORICAL

    x_train, x_test, y_train, y_test = train_test_split(
        df[features],
        df[TARGET],
        test_size=0.2,
        stratify=df[TARGET],
        random_state=SEED,
    )

    pipeline = build_pipeline(C).fit(
        x_train,
        y_train,
    )

    proba = pipeline.predict_proba(x_test)[:, 1]

    pr_auc = float(
        average_precision_score(
            y_test,
            proba,
        )
    )

    precision, recall, thresholds = precision_recall_curve(
        y_test,
        proba,
    )

    threshold = float(
        thresholds[recall[:-1] >= 0.70].max()
    )

    data_md5 = hashlib.md5(
        DATA_PATH.read_bytes()
    ).hexdigest()

    mlflow.set_experiment(EXPERIMENT)

    client = MlflowClient()

    with mlflow.start_run() as run:

        mlflow.log_params({
            "C": C,
            "seed": SEED,
            "data_md5": data_md5,
        })

        mlflow.log_metric(
            "pr_auc",
            pr_auc,
        )

        metadata = {
            "features": features,
            "threshold": round(threshold, 4),
        }

        mlflow.log_dict(
            metadata,
            "metadata.json",
        )

        fig, ax = plt.subplots()

        ax.plot(
            recall,
            precision,
        )

        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_title("Precision-Recall curve")

        mlflow.log_figure(
            fig,
            "pr_curve.png",
        )

        plt.close(fig)

        info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            registered_model_name=MODEL_NAME,
            skops_trusted_types=SKOPS_TRUSTED,
        )

        version = info.registered_model_version

    old_version, old_score = champion_score(client)

    promoted = (
        old_score is None
        or pr_auc > old_score + MIN_GAIN
    )

    client.set_registered_model_alias(
        MODEL_NAME,
        "challenger",
        version,
    )

    if promoted:
        client.set_registered_model_alias(
            MODEL_NAME,
            "champion",
            version,
        )

    result = {
        "run_id": run.info.run_id,
        "version": version,
        "pr_auc": round(pr_auc, 4),
        "champion_before": old_version,
        "champion_pr_auc_before": old_score,
        "promoted": promoted,
    }

    print(
        json.dumps(
            result,
            ensure_ascii=False,
        )
    )

    return result


if __name__ == "__main__":
    main()