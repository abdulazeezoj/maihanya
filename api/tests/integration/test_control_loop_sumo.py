"""One headless integration test: a short scenario run via `sumo` (not
`sumo-gui`) end-to-end through `sumo`, `scheduler`, and `schemas`, catching
integration regressions unit tests (which use fakes) can't see.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mahanya.config import get_config
from mahanya.scheduler import Controller
from mahanya.sumo.traci_client import TraciClient

pytestmark = pytest.mark.integration


def test_control_loop_runs_a_short_scenario_end_to_end():
    config = get_config()
    client = TraciClient(
        config.simulation.sumocfg_path_for("sapon_peak.sumocfg"),
        tls_id=config.simulation.tls_id,
        seed=123,
        step_length=1.0,
        sumo_binary=config.simulation.sumo_binary,
        label="integration-test-control-loop",
    )
    client.start()
    controller = Controller(config.scheduler, dt=1.0, model=None)
    try:
        decisions = controller.run(client, scenario_id="integration-test", num_ticks=60)
    finally:
        client.close()

    assert len(decisions) == 60
    reason_codes = Counter(d.reason_code for d in decisions)
    # Every decision uses one of the five documented reason codes.
    assert set(reason_codes) <= {
        "model_accepted",
        "min_green_hold",
        "max_green_force",
        "anti_starvation_force",
        "emergency_preempt",
    }
    # Never a phase outside the declared 9-state space.
    from mahanya.schemas import ALL_PHASES

    assert all(d.applied_phase in ALL_PHASES for d in decisions)
    # Ticks are strictly increasing, one per control-loop step.
    assert [d.tick for d in decisions] == list(range(60))


def test_control_loop_with_trained_model_if_available():
    """Runs the same scenario through a trained model when a checkpoint is
    present; otherwise skipped (training is a separate offline step)."""

    config = get_config()
    if not config.model.checkpoint_path.exists():
        pytest.skip("no trained model checkpoint available")

    from mahanya.model.infer import ModelRecommender

    model = ModelRecommender.load(config.model.checkpoint_path, config.model)
    client = TraciClient(
        config.simulation.sumocfg_path_for("sapon_peak.sumocfg"),
        tls_id=config.simulation.tls_id,
        seed=456,
        step_length=1.0,
        sumo_binary=config.simulation.sumo_binary,
        label="integration-test-with-model",
    )
    client.start()
    controller = Controller(
        config.scheduler, dt=1.0, model=model, sequence_length=config.model.sequence_length
    )
    try:
        decisions = controller.run(client, scenario_id="integration-test-model", num_ticks=60)
    finally:
        client.close()

    assert len(decisions) == 60
    assert any(d.recommendation is not None for d in decisions)


def test_turning_routes_run_under_single_approach_signal_control():
    """Real SUMO turns occur while each signal phase serves just one approach."""
    import xml.etree.ElementTree as ET

    config = get_config()
    root = ET.parse(config.simulation.net_path).getroot()
    controlled = [c for c in root.findall("connection") if c.get("tl") == config.simulation.tls_id]
    assert len(controlled) == 12
    phases = root.find("tlLogic").findall("phase")
    for index, direction in enumerate(("north", "south", "east", "west")):
        green = phases[index * 2].attrib["state"]
        yellow = phases[index * 2 + 1].attrib["state"]
        for connection in controlled:
            link_index = int(connection.attrib["linkIndex"])
            is_approach = connection.attrib["from"] == f"{direction}_in"
            assert green[link_index] == ("G" if is_approach else "r")
            assert yellow[link_index] == ("y" if is_approach else "r")
    assert set(phases[-1].attrib["state"]) == {"r"}

    client = TraciClient(config.simulation.sumocfg_path, seed=123, label="integration-turning")
    client.start()
    turns_seen = set()
    try:
        for _ in range(800):
            client.advance()
            for vehicle_id in client._conn.vehicle.getIDList():
                route = client._conn.vehicle.getRoute(vehicle_id)
                if route[0] == "north_in" and route[-1] in {"east_out", "west_out"}:
                    angle = client._conn.vehicle.getAngle(vehicle_id)
                    if 95 < angle < 175 or 185 < angle < 265:
                        turns_seen.add(route[-1])
            if turns_seen == {"east_out", "west_out"}:
                break
    finally:
        client.close()
    assert turns_seen == {"east_out", "west_out"}
