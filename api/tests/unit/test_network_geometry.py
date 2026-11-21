"""`network_geometry.load_network_geometry` against the checked-in compiled
network: pure XML parsing, no running SUMO process required.
"""

from __future__ import annotations

from pathlib import Path

from mahanya.config import Config
from mahanya.sumo.network_geometry import load_network_geometry


def test_load_network_geometry_covers_all_four_approach_in_lanes():
    settings = Config()
    geometry = load_network_geometry(settings.simulation.net_path)

    in_lanes = {lane.direction: lane for lane in geometry.lanes if lane.kind == "in"}
    assert set(in_lanes) == {"north", "south", "east", "west"}
    for lane in in_lanes.values():
        assert len(lane.shape) >= 2
        assert lane.width_meters == 3.2


def test_load_network_geometry_bounds_are_nonzero_extent():
    settings = Config()
    geometry = load_network_geometry(settings.simulation.net_path)

    assert geometry.bounds.max_x > geometry.bounds.min_x
    assert geometry.bounds.max_y > geometry.bounds.min_y


def test_load_network_geometry_skips_internal_junction_edges():
    settings = Config()
    geometry = load_network_geometry(settings.simulation.net_path)

    assert all(not lane.edge_id.startswith(":") for lane in geometry.lanes)


def test_load_network_geometry_reads_explicit_lane_width(tmp_path: Path) -> None:
    network = tmp_path / "network.xml"
    network.write_text(
        '<net><location convBoundary="0,0,20,20"/>'
        '<edge id="north_in"><lane id="north_in_0" width="3.7" '
        'shape="10,20 10,11"/></edge></net>',
        encoding="utf-8",
    )
    assert load_network_geometry(network).lanes[0].width_meters == 3.7
