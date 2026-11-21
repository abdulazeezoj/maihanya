"""Durable run-scoped tick records for inspection and later data preparation.

Records are observations and applied scheduler decisions, not validated labels.
SQLite is local to this installation and is not a backup.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mahanya.config import Config
from mahanya.schemas import DecisionLogRecord


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(config: Config, sumocfg: Path, model_loaded: bool) -> dict[str, Any]:
    """Identify the actual inputs without asserting that field data is real."""
    root = ET.parse(sumocfg).getroot()
    route_file = root.find("./input/route-files")
    routes = [] if route_file is None else (route_file.get("value") or "").split(",")
    net_file = root.find("./input/net-file")
    net_name = net_file.get("value") if net_file is not None else None
    return {
        "record_schema_version": 1,
        "config": config.model_dump(mode="json"),
        "model_loaded": model_loaded,
        "model_sha256": _sha256(config.model.checkpoint_path) if model_loaded else None,
        "network_sha256": _sha256(sumocfg.parent / net_name) if net_name else None,
        "sumocfg_sha256": _sha256(sumocfg),
        "route_sha256": {name: _sha256(sumocfg.parent / name) for name in routes},
        "raw_counts_sha256_at_run_start": _sha256(config.raw_counts_csv),
        "label_provenance": "applied scheduler decision; not independently validated ground truth",
    }


class RunStore:
    """SQLite-backed append-only tick records, isolated by run ID."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, seed INTEGER NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticks (
                    run_id TEXT NOT NULL REFERENCES runs(id), tick INTEGER NOT NULL,
                    record_json TEXT NOT NULL, PRIMARY KEY (run_id, tick)
                );
                CREATE INDEX IF NOT EXISTS runs_started ON runs(started_at DESC);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn

    def start(self, scenario_id: str, seed: int, metadata: dict[str, Any]) -> str:
        run_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, NULL, 'running', ?)",
                (run_id, scenario_id, seed, datetime.now(UTC).isoformat(), json.dumps(metadata)),
            )
        return run_id

    def append(self, run_id: str, record: DecisionLogRecord) -> None:
        if record.state.tick != record.decision.tick:
            raise ValueError("state and decision ticks do not match")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO ticks (run_id, tick, record_json) VALUES (?, ?, ?)",
                (run_id, record.state.tick, record.model_dump_json(by_alias=True)),
            )

    def finish(self, run_id: str, status: str) -> None:
        if status not in {"completed", "stopped", "failed"}:
            raise ValueError("invalid terminal run status")
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status=?, ended_at=? WHERE id=? AND status='running'",
                (status, datetime.now(UTC).isoformat(), run_id),
            )

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "scenarioId": row["scenario_id"],
            "seed": row["seed"],
            "startedAt": row["started_at"],
            "endedAt": row["ended_at"],
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"]),
        }

    def list_runs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._run(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def ticks(self, run_id: str, after_tick: int = -1, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT record_json FROM ticks WHERE run_id=? AND tick>? ORDER BY tick LIMIT ?",
                (run_id, after_tick, limit),
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]
