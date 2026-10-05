import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mlflow import MlflowClient
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from roi_service import db
from roi_service.config import settings

PREDICTIONS = Counter("roi_predictions_total", "Predictions by class", ["churn"])
SCORE = Histogram("roi_score", "Predicted roi", buckets=[i / 10 for i in range(11)])
MODEL_INFO = Gauge("roi_model_info", "Model loaded by this pod", ["version"])
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)  # штатные 0.1, 0.5, 1 с слишком грубые

class Features(BaseModel):
    model_config = {"extra": "forbid"}

    major: str = Field(min_length=1, max_length=100)
    institution_tier: str = Field(min_length=1, max_length=50)
    region: str = Field(min_length=1, max_length=50)
    institution_selectivity_pctile: int = Field(ge=0, le=100)
    had_internship: int = Field(ge=0, le=1)
    gpa: float | None = Field(default=None, ge=0, le=4.0)
    net_cost_usd: int | None = Field(default=None, ge=0, le=1_000_000)

class Prediction(BaseModel):
    #model_config = {"protected_namespaces": ()}

    score: float          # вероятность окупаемости
    churn: int            # решение по порогу (0/1)
    model_version: str
    request_id: str
    latency_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_name = os.getenv("MODEL_NAME")
    model_alias = os.getenv("MODEL_ALIAS", "champion")

    if model_name:
        tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI",
            "http://mlflow.mlops:5000",
        )

        mlflow.set_tracking_uri(tracking_uri)
        client = MlflowClient()

        model_version = client.get_model_version_by_alias(
            model_name,
            model_alias,
        )

        model_uri = f"models:/{model_name}@{model_alias}"

        app.state.pipeline = mlflow.sklearn.load_model(model_uri)
        app.state.version = model_version.version

        metadata_path = client.download_artifacts(
            model_version.run_id,
            "metadata.json",
        )

        metadata = json.loads(
            Path(metadata_path).read_text(encoding="utf-8")
        )

        app.state.meta = metadata
        app.state.threshold = float(metadata.get("threshold", 0.5))

    else:
        bundle = joblib.load(settings.model_path)

        app.state.pipeline = bundle["pipeline"]
        app.state.meta = bundle["metadata"]
        app.state.version = bundle["metadata"]["model_version"]
        app.state.threshold = float(
            bundle["metadata"].get("threshold", 0.5)
        )

    db.init()

    yield

    app.state.pipeline = None

app = FastAPI(title="roi-service", version="1.0", lifespan=lifespan)
Instrumentator().instrument(app, latency_lowr_buckets=LATENCY_BUCKETS).expose(app)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_version": getattr(app.state, "version", "unknown"),
        "prediction_threshold": getattr(app.state, "threshold", None),
    }

@app.get("/ready")
def ready():
    if getattr(app.state, "pipeline", None) is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    return {"status": "ready"}


@app.post("/v1/predict")
def predict(x: Features, bg: BackgroundTasks) -> Prediction:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    payload = x.model_dump()  # x.dict() in pydantic v1
    frame = pd.DataFrame([payload]).reindex(columns=app.state.meta["features"])

    score = float(app.state.pipeline.predict_proba(frame)[0, 1])

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    bg.add_task(db.save_prediction, request_id, payload, score, app.state.version, latency_ms, status_code=200)

    churn = score >= app.state.meta["threshold"]

    PREDICTIONS.labels(str(churn).lower()).inc()
    SCORE.observe(score)
    
    return Prediction(score=score, churn=churn, model_version = app.state.version, request_id=request_id, latency_ms=latency_ms)


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    content = {"detail": jsonable_encoder(exc.errors())}
    if request.url.path != "/v1/predict":
        return JSONResponse(status_code=422, content=content)

    body = exc.body if isinstance(exc.body, dict) else {"raw": str(exc.body)}
    task = BackgroundTask(
        db.save_prediction, str(uuid.uuid4()), body, None, request.app.state.version, None, 422
    )
    return JSONResponse(status_code=422, content=content, background=task)