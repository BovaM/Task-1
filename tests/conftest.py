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
        "major": "biology",
        "institution_tier": "mid_tier",
        "region": "south",
        "institution_selectivity_pctile": 52,
        "had_internship": 0,
        "gpa": 2.58,
        "net_cost_usd": 144400
    }
