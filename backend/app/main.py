"""FastAPI app: every route under /api (Firebase Hosting rewrites /api/** to Cloud Run).

Auth (Firebase ID token) and the Gemini routes (/notes, /calendar/refresh) arrive with the GCP
setup; until then the app runs fully on the JSON seed store.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import service
from app.store import JsonStore, Store

store: Store = JsonStore()
api = APIRouter(prefix="/api")


class PlanRequest(BaseModel):
    horizon_weeks: int = Field(service.HORIZON_WEEKS, ge=1, le=26)


class ScenarioRequest(BaseModel):
    crop: str
    week: date
    harvest_pct: float = Field(100, ge=0, le=150)


@api.get("/health")
def health() -> dict:
    return {"ok": True}


@api.get("/state")
def state() -> dict:
    return {
        "today": service.today(store),
        "synthetic": store.meta().get("synthetic", True),
        **{c: store.list(c) for c in ("crops", "farmers", "partners", "households", "batches", "signals")},
    }


@api.post("/forecast/run")
def forecast_run(req: PlanRequest = PlanRequest()) -> dict:
    return {"today": service.today(store), "series": service.forecast_view(store, req.horizon_weeks)}


@api.post("/plan/run")
def plan_run(req: PlanRequest = PlanRequest()) -> dict:
    return {"today": service.today(store), "plans": service.run_plan(store, req.horizon_weeks)}


@api.post("/scenario")
def scenario(req: ScenarioRequest) -> dict:
    if req.crop not in service.crops(store):
        raise HTTPException(404, f"unknown crop {req.crop!r}")
    return service.run_scenario(store, req.crop, req.week, req.harvest_pct)


@api.post("/demo/reset")
def demo_reset() -> dict:
    store.reset()
    return {"ok": True}


app = FastAPI(title="Tanam Secukupnya", version="0.1.0")
app.include_router(api)
