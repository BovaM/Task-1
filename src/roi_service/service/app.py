import time
import uuid
import os

from contextlib import asynccontextmanager

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

import joblib
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from pydantic import BaseModel, Field

from roi_service import db
from roi_service.config import settings

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
    bundle = joblib.load(settings.model_path)
    app.state.pipeline = bundle["pipeline"]
    app.state.meta = bundle["metadata"]
    app.state.version = bundle["metadata"]["model_version"]

    db.init()
    yield
    app.state.pipeline = None


app = FastAPI(title="roi-service", version="1.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_version": getattr(app.state, "version", "unknown"),
        "prediction_threshold": os.environ.get("PREDICTION_THRESHOLD"),
    }

@app.get("/ready")
def ready():
    if getattr(app.state, "pipeline", "None") is  None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
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