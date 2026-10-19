"""Проверка данных: схема pandera на выгрузку, отчёт в MLflow.

    uv run python -m roi_service.data_check     код выхода 1 и тег valid=false при нарушениях

    Пороги подобраны по выгрузке data/college_major_roi.csv:
    describe() и доли классов - см. notebooks/analyze_data.py и AUDIT.md.
"""

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

DATA_PATH = Path(os.getenv("DATA_PATH", "data/college_major_roi.csv"))
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "roi")

ALLOWED_MAJORS = {
    "biology", "business", "business_analytics", "chemical_engineering", "communications",
    "computer_engineering", "computer_science", "criminal_justice", "economics", "education",
    "electrical_engineering", "finance", "fine_arts", "humanities", "marketing",
    "mechanical_engineering", "nursing", "psychology", "social_work",
}
ALLOWED_TIERS = {"for_profit", "ivy_elite", "mid_tier", "regional", "top_public"}
ALLOWED_REGIONS = {"midwest", "northeast", "south", "west"}

MIN_ROWS = 20_000
POSITIVE_SHARE = (0.7, 0.95)
NET_COST_MEDIAN = (50_000, 120_000)
MAX_GPA_MISSING = 0.1

ROWS = pa.DataFrameSchema(
    {
        "major": pa.Column(str, pa.Check.isin(ALLOWED_MAJORS)),
        "institution_tier": pa.Column(str, pa.Check.isin(ALLOWED_TIERS)),
        "region": pa.Column(str, pa.Check.isin(ALLOWED_REGIONS)),
        "institution_selectivity_pctile": pa.Column(int, pa.Check.in_range(0, 102), coerce=True),
        "had_internship": pa.Column(int, pa.Check.isin([0, 1]), coerce=True),
        "gpa": pa.Column(float, pa.Check.in_range(0, 4.0), nullable=True, coerce=True),
        "net_cost_usd": pa.Column(float, pa.Check.in_range(0, 1_000_000), nullable=True, coerce=True),
        "positive_roi": pa.Column(int, pa.Check.isin([0, 1]), coerce=True),
    },
    strict=False,)


EXPORT = pa.DataFrameSchema(
    ROWS.columns,
    checks=[
        pa.Check(lambda df: len(df) >= MIN_ROWS, error=f"меньше {MIN_ROWS} строк: выгрузка неполная"),
        pa.Check(lambda df: POSITIVE_SHARE[0] <= df["positive_roi"].mean() <= POSITIVE_SHARE[1],
                 error="доля positive_roi вне коридора: сменилась разметка?"),
        pa.Check(lambda df: NET_COST_MEDIAN[0] <= df["net_cost_usd"].median() <= NET_COST_MEDIAN[1],
                 error="медиана net_cost_usd вне коридора: сменились единицы?"),
        pa.Check(lambda df: df["gpa"].isna().mean() <= MAX_GPA_MISSING, error="слишком много пропусков в gpa"),
        pa.Check(lambda df: df["grad_id"].is_unique, error="grad_id не уникален"),
    ],
    strict=False,
)


def file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest() 


def main() -> int:
    import mlflow

    from roi_service.config import settings

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    df = pd.read_csv(DATA_PATH)
    md5 = file_md5(DATA_PATH)
    with mlflow.start_run(run_name="validate"):
        mlflow.log_params({"step": "validate", "data": str(DATA_PATH), "data_md5": md5})
        mlflow.log_metric("rows", len(df))
        try:
            EXPORT.validate(df, lazy=True)
        except pa.errors.SchemaErrors as e:
            fc = e.failure_cases
            summary = fc.groupby(["column", "check"], dropna=False).size().rename("cases").reset_index()
            with tempfile.TemporaryDirectory() as tmp:
                fc.head(1000).to_csv(Path(tmp) / "failure_cases.csv", index=False)
                mlflow.log_artifact(str(Path(tmp) / "failure_cases.csv"))
            mlflow.log_metric("failed_checks", len(summary))
            mlflow.set_tag("valid", "false")
            print("данные не прошли проверку, отчёт failure_cases.csv в MLflow:")
            print(summary.to_string(index=False))
            return 1
        mlflow.set_tag("valid", "true")
    print(f"данные валидны: {len(df)} строк, md5 {md5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
