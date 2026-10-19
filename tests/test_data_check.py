import pandas as pd
import pandera.pandas as pa
import pytest

from roi_service.data_check import EXPORT, MIN_ROWS, ROWS


def sample(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "grad_id": [f"G{i:06d}" for i in range(n)],
        "major": ["biology"] * n,
        "institution_tier": ["mid_tier"] * n,
        "region": ["south"] * n,
        "institution_selectivity_pctile": [52] * n,
        "had_internship": [1] * n,
        "gpa": [3.2] * n,
        "net_cost_usd": [80_000.0] * n,
        "positive_roi": [1, 0] * (n // 2) + [1] * (n % 2),
    })


def test_good_rows_pass():
    ROWS.validate(sample(), lazy=True)


def test_corrupted_value_is_caught():
    df = sample()
    df.loc[0, "gpa"] = 7.0
    with pytest.raises(pa.errors.SchemaErrors) as e:
        ROWS.validate(df, lazy=True)
    assert "gpa" in set(e.value.failure_cases["column"])


def test_unknown_tier_is_caught():
    df = sample()
    df.loc[0, "institution_tier"] = "unknown_tier"
    with pytest.raises(pa.errors.SchemaErrors):
        ROWS.validate(df, lazy=True)


def test_units_corruption_is_caught():
    """Проверка, что net_cost_usd из долларов не перешел в центы"""
    df = sample(n=10)
    df["net_cost_usd"] = df["net_cost_usd"] * 100
    with pytest.raises(pa.errors.SchemaErrors) as e:
        ROWS.validate(df, lazy=True)
    assert "net_cost_usd" in set(e.value.failure_cases["column"])


def test_small_export_rejected():
    """Полная выгрузка, но меньше MIN_ROWS"""
    n = 50
    df = sample(n=n)
    df["positive_roi"] = [1] * n
    assert n < MIN_ROWS
    with pytest.raises(pa.errors.SchemaErrors) as e:
        EXPORT.validate(df, lazy=True)
    assert any("строк" in str(c) for c in e.value.failure_cases["check"])


def test_duplicate_grad_id_rejected():
    df = sample(n=6)
    df.loc[1, "grad_id"] = df.loc[0, "grad_id"]
    with pytest.raises(pa.errors.SchemaErrors) as e:
        EXPORT.validate(df, lazy=True)
    assert any("grad_id" in str(c) for c in e.value.failure_cases["check"])
