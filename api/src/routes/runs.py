"""Read durable simulation runs and their ordered, paginated tick records."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import get_run_store
from mahanya.data.run_store import RunStore

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: RunStore = Depends(get_run_store),
) -> list[dict[str, Any]]:
    return store.list_runs(limit, offset)


@router.get("/{run_id}")
def get_run(run_id: str, store: RunStore = Depends(get_run_store)) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/ticks")
def get_ticks(
    run_id: str,
    after_tick: int = Query(default=-1, ge=-1),
    limit: int = Query(default=100, ge=1, le=500),
    store: RunStore = Depends(get_run_store),
) -> list[dict[str, Any]]:
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return store.ticks(run_id, after_tick, limit)
