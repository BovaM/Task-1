import pytest
from fastapi.testclient import TestClient

from roi_service.service.app import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def good_row():
    return {
        "major": "medicine",
        "institution_tier": "top",
        "region": "USA",
        "institution_selectivity_pctile": 35,
        "had_internship": 1,
        "gpa": 3.0,
        "net_cost_usd": 500000
    }
