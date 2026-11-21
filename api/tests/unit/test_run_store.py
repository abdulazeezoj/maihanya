"""Run-scoped tick persistence, pagination, and export boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cli import main as cli_main
from core.app import create_app
from core.deps import get_run_store
from mahanya.config import get_config
from mahanya.data.run_store import RunStore
from mahanya.schemas import DecisionLogRecord, SchedulerDecision
from tests.fixtures.traffic import make_traffic_state


def _record(tick: int, scenario: str = "sapon-peak") -> DecisionLogRecord:
    state = make_traffic_state(tick=tick, scenario_id=scenario)
    decision = SchedulerDecision(
        tick=tick,
        timestamp=state.timestamp,
        recommendation=None,
        applied_phase="NORTH_GREEN",
        reason_code="model_accepted",
    )
    return DecisionLogRecord(state=state, decision=decision)


def test_run_store_isolates_restarted_and_concurrent_runs_and_paginates(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    store = RunStore(path)
    first = store.start("sapon-peak", 123, {"model_loaded": False})
    other = store.start("sapon-offpeak", 456, {"model_loaded": False})
    for tick in range(3):
        store.append(first, _record(tick))
    store.append(other, _record(0, "sapon-offpeak"))
    # A separate connection can inspect a still-running run immediately.
    reader = RunStore(path)
    assert reader.get_run(first)["status"] == "running"
    assert [r["state"]["tick"] for r in reader.ticks(first, limit=2)] == [0, 1]
    assert [r["state"]["tick"] for r in reader.ticks(first, after_tick=1)] == [2]
    assert reader.ticks(other)[0]["state"]["scenarioId"] == "sapon-offpeak"
    store.finish(first, "stopped")
    restarted = store.start("sapon-peak", 123, {})
    store.append(restarted, _record(0))
    assert len({first, other, restarted}) == 3
    assert reader.get_run(first)["status"] == "stopped"
    assert len(reader.ticks(first)) == 3
    assert len(reader.ticks(restarted)) == 1


def test_runs_api_supports_inspection_while_running(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run_id = store.start("sapon-peak", 1, {"source": "simulation"})
    store.append(run_id, _record(0))
    store.append(run_id, _record(1))
    app = create_app()
    app.dependency_overrides[get_run_store] = lambda: store
    with TestClient(app) as client:
        assert client.get("/api/runs").json()[0]["id"] == run_id
        assert client.get(f"/api/runs/{run_id}").json()["metadata"]["source"] == "simulation"
        response = client.get(f"/api/runs/{run_id}/ticks?after_tick=0&limit=1")
        assert response.status_code == 200
        assert response.json()[0]["state"]["tick"] == 1
        assert client.get("/api/runs/missing/ticks").status_code == 404
        assert client.get(f"/api/runs/{run_id}/ticks?limit=0").status_code == 422


def test_export_run_writes_ticks_and_metadata_without_overwriting(
    tmp_path: Path, monkeypatch
) -> None:
    config = get_config()
    path = tmp_path / "runs.sqlite3"
    config = config.model_copy(
        update={"dashboard": config.dashboard.model_copy(update={"run_store_path": path})}
    )
    monkeypatch.setattr(cli_main, "get_config", lambda: config)
    store = RunStore(path)
    run_id = store.start("sapon-peak", 9, {"model_loaded": False})
    store.append(run_id, _record(0))
    output = tmp_path / "ticks.jsonl"
    runner = CliRunner()
    result = runner.invoke(cli_main.app, ["export-run", run_id, "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["state"]["tick"] == 0
    sidecar = output.with_name(output.name + ".metadata.json")
    assert json.loads(sidecar.read_text(encoding="utf-8"))["id"] == run_id
    assert (
        runner.invoke(cli_main.app, ["export-run", run_id, "--output", str(output)]).exit_code != 0
    )
