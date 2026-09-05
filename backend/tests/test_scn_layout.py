"""The RF sensor and channel layout. Spec: scn-005.

The layout is the fixed part of the synthetic RF side: which sensors exist,
where they stand, which channels they report on, and how often. Everything
that varies per run -- noise amplitude, which sensors are affected, when the
event starts -- belongs to `scn-002`, not here.

Three groups of tests, and the middle one is the reason the item exists:

* **The shipped layout is the artefact under test.** Every claim made about it
  in `docs/em_fusion_v2.md` section 5 is asserted here against the file, so the
  document and the configuration cannot drift apart silently.
* **A layout that is not discriminating is rejected at load.** "Sensors are
  positioned so that a candidate interference zone contains some and excludes
  others" (FR-109) is untestable as prose. It becomes testable as two
  invariants at a recorded radius: every sensor has at least one other sensor
  *within* it, or `anom-007` has no neighbour to compare against; and at least
  one *beyond* it, or every zone contains everything and `anom-005` cannot
  discriminate. Both are checked here in both directions -- a layout that
  violates either must fail loudly rather than be accepted and produce
  meaningless anomalies six phases later.
* **The accessors the detectors will call.** `neighbours` and
  `adjacent_channels` are the layout's whole interface to Phase 6, and getting
  them wrong is a silent wrong-answer bug rather than a crash.

Nothing here touches a database. Distances are computed in the layout itself
rather than by PostGIS, because the layout is validated at load time, before
any connection exists and before any observation has been written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.scenario.layout import (
    DEFAULT_LAYOUT_PATH,
    L1_CENTRE_MHZ,
    LayoutError,
    RfLayout,
    load_layout,
)

#: The corpus bounding box, from `data/opensky/manifest.json`. A sensor outside
#: it would report on airspace the replay never covers.
BOX = {"lat_min": 49.0, "lat_max": 54.0, "lon_min": 3.0, "lon_max": 11.0}

#: The channel plan, from `docs/em_fusion_v2.md` section 5. Written out rather
#: than generated from a step, so a wrong step size in the implementation is
#: caught instead of reproduced.
CENTRES_MHZ = (
    1567.42,
    1569.42,
    1571.42,
    1573.42,
    1575.42,
    1577.42,
    1579.42,
    1581.42,
)

#: Great-circle distances between the shipped sensors, in km, for every pair
#: closer than the widest radius the layout is asserted to work at.
PAIR_DISTANCES_KM = {
    ("RF-01", "RF-02"): 45.34,
    ("RF-01", "RF-03"): 54.13,
    ("RF-04", "RF-05"): 55.75,
    ("RF-05", "RF-06"): 55.54,
    ("RF-06", "RF-07"): 53.93,
    ("RF-02", "RF-04"): 85.71,
    ("RF-02", "RF-03"): 92.98,
}


@pytest.fixture()
def shipped() -> RfLayout:
    return load_layout()


def _write(tmp_path: Path, document: Any) -> Path:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(document))
    return path


def _mutated(tmp_path: Path, mutate: Any) -> Path:
    """The shipped layout as a plain document, with one thing changed.

    Starting from the real file rather than a minimal fixture means each
    rejection test proves that *this* layout is one edit away from invalid --
    which is how a layout would actually be broken.
    """
    document = json.loads(DEFAULT_LAYOUT_PATH.read_text())
    mutate(document)
    return _write(tmp_path, document)


# --------------------------------------------------------------------------
# The shipped layout
# --------------------------------------------------------------------------


# spec: scn-005 -- the packaged default loads with no argument, because the
# generator and every detector get their layout this way.
def test_default_layout_loads(shipped: RfLayout) -> None:
    assert isinstance(shipped, RfLayout)


# spec: scn-005 -- six to eight sensors (FR-108).
def test_sensor_count_is_within_the_specified_range(shipped: RfLayout) -> None:
    assert 6 <= len(shipped.sensors) <= 8


# spec: scn-005
def test_sensor_ids_and_positions_are_unique(shipped: RfLayout) -> None:
    ids = [s.sensor_id for s in shipped.sensors]
    positions = [(s.lat, s.lon) for s in shipped.sensors]
    assert len(set(ids)) == len(ids)
    assert len(set(positions)) == len(positions)


# spec: scn-005 -- a sensor outside the corpus bounding box would watch
# airspace the replayed telemetry never covers, so anom-005 could never fuse
# its readings with a track cluster.
def test_every_sensor_stands_inside_the_corpus_bounding_box(shipped: RfLayout) -> None:
    for sensor in shipped.sensors:
        assert BOX["lat_min"] <= sensor.lat <= BOX["lat_max"], sensor.sensor_id
        assert BOX["lon_min"] <= sensor.lon <= BOX["lon_max"], sensor.sensor_id


# spec: scn-005 -- eight channels, contiguous indices, the specified centres.
def test_channel_plan_matches_the_specification(shipped: RfLayout) -> None:
    assert tuple(c.index for c in shipped.channels) == tuple(range(8))
    assert tuple(c.centre_frequency_mhz for c in shipped.channels) == CENTRES_MHZ
    assert all(c.bandwidth_mhz == 2.0 for c in shipped.channels)


# spec: scn-005 -- one channel exactly on GNSS L1, with four below and three
# above. The spec previously said "four either side", which needs nine
# channels; the frequency list is the authority and the sentence was wrong.
def test_one_channel_sits_exactly_on_l1_with_neighbours_both_ways(
    shipped: RfLayout,
) -> None:
    on_l1 = [c for c in shipped.channels if c.centre_frequency_mhz == L1_CENTRE_MHZ]
    assert len(on_l1) == 1
    l1 = on_l1[0]
    below = [c for c in shipped.channels if c.index < l1.index]
    above = [c for c in shipped.channels if c.index > l1.index]
    assert len(below) == 4
    assert len(above) == 3


# spec: scn-005 -- a fixed interval of simulated time.
def test_the_interval_is_a_positive_whole_number_of_seconds(
    shipped: RfLayout,
) -> None:
    assert shipped.interval_seconds > 0


# --------------------------------------------------------------------------
# Discrimination -- the property FR-109 asks for, in both directions
# --------------------------------------------------------------------------


# spec: scn-005 -- every sensor has a neighbour, or anom-007's neighbour test
# is vacuous for it.
def test_every_sensor_has_at_least_one_neighbour(shipped: RfLayout) -> None:
    for sensor in shipped.sensors:
        assert shipped.neighbours(sensor.sensor_id), sensor.sensor_id


# spec: scn-005 -- every sensor has a non-neighbour, or a zone centred on it
# contains the whole layout and anom-005 cannot discriminate.
def test_every_sensor_has_at_least_one_sensor_beyond_the_radius(
    shipped: RfLayout,
) -> None:
    for sensor in shipped.sensors:
        inside = set(shipped.neighbours(sensor.sensor_id)) | {sensor.sensor_id}
        outside = {s.sensor_id for s in shipped.sensors} - inside
        assert outside, sensor.sensor_id


# spec: scn-005 -- the property must not be knife-edge. If it held only at the
# exact configured radius, any later adjustment to a position or to anom-005's
# configured distance would silently destroy it.
@pytest.mark.parametrize("radius_km", [60.0, 70.0, 80.0])
def test_the_layout_discriminates_across_a_band_of_radii(
    shipped: RfLayout, radius_km: float
) -> None:
    for sensor in shipped.sensors:
        near = shipped.neighbours(sensor.sensor_id, radius_km=radius_km)
        assert near, (sensor.sensor_id, radius_km)
        assert len(near) + 1 < len(shipped.sensors), (sensor.sensor_id, radius_km)


# spec: scn-005 -- a layout in which some sensor stands alone is rejected.
def test_an_isolated_sensor_is_rejected(tmp_path: Path) -> None:
    def strand(document: Any) -> None:
        document["sensors"][0]["lat"] = 49.1
        document["sensors"][0]["lon"] = 3.1

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, strand))


# spec: scn-005 -- the stated failure case: every sensor inside every
# plausible affected area.
def test_a_radius_that_swallows_the_whole_layout_is_rejected(tmp_path: Path) -> None:
    def swallow(document: Any) -> None:
        document["discrimination_radius_km"] = 500.0

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, swallow))


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------


# spec: scn-005 -- fewer than six sensors makes clustering and the neighbour
# test barely meaningful (docs/em_fusion_v2.md section 5).
def test_too_few_sensors_is_rejected(tmp_path: Path) -> None:
    def trim(document: Any) -> None:
        document["sensors"] = document["sensors"][:5]

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, trim))


# spec: scn-005
def test_duplicate_sensor_ids_are_rejected(tmp_path: Path) -> None:
    def collide(document: Any) -> None:
        document["sensors"][1]["sensor_id"] = document["sensors"][0]["sensor_id"]

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, collide))


# spec: scn-005 -- two sensors at one point are one sensor reported twice, and
# would double-count in any spatial cluster.
def test_duplicate_sensor_positions_are_rejected(tmp_path: Path) -> None:
    def stack(document: Any) -> None:
        document["sensors"][1]["lat"] = document["sensors"][0]["lat"]
        document["sensors"][1]["lon"] = document["sensors"][0]["lon"]

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, stack))


# spec: scn-005 -- the second stated failure case: no channel on L1 removes
# the band gnss-degradation targets.
def test_a_plan_with_no_channel_on_l1_is_rejected(tmp_path: Path) -> None:
    def detune(document: Any) -> None:
        for channel in document["channels"]:
            channel["centre_frequency_mhz"] += 0.5

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, detune))


# spec: scn-005 -- adjacency by index must be adjacency in frequency, or
# anom-007's frequency-neighbour test compares unrelated channels.
def test_non_contiguous_channel_indices_are_rejected(tmp_path: Path) -> None:
    def skip(document: Any) -> None:
        document["channels"][5]["index"] = 9

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, skip))


# spec: scn-005
def test_channels_out_of_frequency_order_are_rejected(tmp_path: Path) -> None:
    def swap(document: Any) -> None:
        a, b = document["channels"][2], document["channels"][3]
        a["centre_frequency_mhz"], b["centre_frequency_mhz"] = (
            b["centre_frequency_mhz"],
            a["centre_frequency_mhz"],
        )

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, swap))


# spec: scn-005 -- L1 at the edge of the plan leaves adjacency running one way
# only, which is the arrangement the "both directions" constraint forbids.
def test_l1_at_the_edge_of_the_plan_is_rejected(tmp_path: Path) -> None:
    def shift(document: Any) -> None:
        for offset, channel in enumerate(document["channels"]):
            channel["centre_frequency_mhz"] = L1_CENTRE_MHZ + 2.0 * offset

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, shift))


# spec: scn-005 -- a zero interval emits every reading at one instant.
def test_a_non_positive_interval_is_rejected(tmp_path: Path) -> None:
    def stop_time(document: Any) -> None:
        document["interval_seconds"] = 0

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, stop_time))


# spec: scn-005 -- a zero radius makes every sensor its own island, which the
# neighbour invariant would catch, but the value is meaningless on its own.
def test_a_non_positive_radius_is_rejected(tmp_path: Path) -> None:
    def collapse(document: Any) -> None:
        document["discrimination_radius_km"] = 0.0

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, collapse))


# spec: scn-005 -- third failure case: a missing file fails loudly, naming the
# path, before any observation is generated.
def test_a_missing_file_is_reported_with_its_path(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere.json"
    with pytest.raises(LayoutError) as raised:
        load_layout(missing)
    assert str(missing) in str(raised.value)


# spec: scn-005 -- third failure case, malformed rather than absent.
def test_unparseable_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    path.write_text("{not json")
    with pytest.raises(LayoutError):
        load_layout(path)


# spec: scn-005 -- third failure case, structurally valid but wrong. An
# unknown key is a misspelling of a known one often enough that accepting it
# silently would apply a default the author believed they had overridden.
def test_an_unknown_key_is_rejected(tmp_path: Path) -> None:
    def misspell(document: Any) -> None:
        document["interval_second"] = document.pop("interval_seconds")

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, misspell))


# spec: scn-005
def test_a_missing_required_key_is_rejected(tmp_path: Path) -> None:
    def drop(document: Any) -> None:
        del document["channels"]

    with pytest.raises(LayoutError):
        load_layout(_mutated(tmp_path, drop))


# --------------------------------------------------------------------------
# The accessors Phase 6 will call
# --------------------------------------------------------------------------


# spec: scn-005 -- distances are great-circle, not planar, and the expected
# values are computed independently of the implementation.
@pytest.mark.parametrize(("pair", "expected_km"), sorted(PAIR_DISTANCES_KM.items()))
def test_distance_between_sensors(
    shipped: RfLayout, pair: tuple[str, str], expected_km: float
) -> None:
    assert shipped.distance_km(*pair) == pytest.approx(expected_km, abs=0.05)
    assert shipped.distance_km(pair[1], pair[0]) == pytest.approx(expected_km, abs=0.05)


# spec: scn-005 -- the neighbour sets anom-007 will use, nearest first.
@pytest.mark.parametrize(
    ("sensor_id", "expected"),
    [
        ("RF-01", ["RF-02", "RF-03"]),
        ("RF-02", ["RF-01"]),
        ("RF-03", ["RF-01"]),
        ("RF-04", ["RF-05"]),
        ("RF-05", ["RF-06", "RF-04"]),
        ("RF-06", ["RF-07", "RF-05"]),
        ("RF-07", ["RF-06"]),
    ],
)
def test_neighbours_at_the_configured_radius(
    shipped: RfLayout, sensor_id: str, expected: list[str]
) -> None:
    assert list(shipped.neighbours(sensor_id)) == expected


# spec: scn-005 -- a sensor is not its own neighbour; anom-007 compares a
# sensor against others.
def test_a_sensor_is_not_its_own_neighbour(shipped: RfLayout) -> None:
    for sensor in shipped.sensors:
        assert sensor.sensor_id not in shipped.neighbours(sensor.sensor_id)


# spec: scn-005 -- an unknown sensor is a caller bug, not an empty result.
def test_neighbours_of_an_unknown_sensor_raises(shipped: RfLayout) -> None:
    with pytest.raises(KeyError):
        shipped.neighbours("RF-99")


# spec: scn-005 -- frequency adjacency, in both directions from L1 and in one
# direction at the ends of the plan.
@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, [1]), (3, [2, 4]), (4, [3, 5]), (6, [5, 7]), (7, [6])],
)
def test_adjacent_channels(
    shipped: RfLayout, index: int, expected: list[int]
) -> None:
    assert list(shipped.adjacent_channels(index)) == expected


# spec: scn-005 -- an index off the end of the plan is a caller bug.
def test_adjacent_channels_of_an_unknown_index_raises(shipped: RfLayout) -> None:
    with pytest.raises(KeyError):
        shipped.adjacent_channels(8)


# spec: scn-005 -- the layout is configuration: an alternative file is loaded
# and used without editing any code that consumes it.
def test_an_alternative_layout_file_is_loaded_in_place_of_the_default(
    tmp_path: Path, shipped: RfLayout
) -> None:
    def rename(document: Any) -> None:
        for sensor in document["sensors"]:
            sensor["sensor_id"] = sensor["sensor_id"].replace("RF", "ALT")

    other = load_layout(_mutated(tmp_path, rename))
    assert [s.sensor_id for s in other.sensors] != [
        s.sensor_id for s in shipped.sensors
    ]
    assert all(s.sensor_id.startswith("ALT-") for s in other.sensors)
