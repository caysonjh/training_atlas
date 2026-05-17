from types import SimpleNamespace

from shapely.geometry import LineString

from app.models import ActivityType
from app.services.coverage import _as_multiline, calculate_new_coverage, normalize_track
from app.services.strava import atlas_type_for


def test_normalize_track_filters_invalid_points():
    line = normalize_track([[37.0, -122.0], [999.0, 999.0], [37.1, -122.1]])
    assert isinstance(line, LineString)
    assert list(line.coords)[0] == (-122.0, 37.0)


def test_swim_requires_gps():
    assert atlas_type_for({"sport_type": "Swim", "start_latlng": []}) is None
    assert atlas_type_for({"sport_type": "Swim", "start_latlng": [1, 2]}) == ActivityType.open_water_swimming


def test_multiline_conversion_handles_line():
    line = LineString([(0, 0), (1, 1)])
    multi = _as_multiline(line)
    assert multi.geom_type == "MultiLineString"


def test_repeated_route_adds_no_new_coverage():
    line = LineString([(0, 0), (1, 1)])
    assert calculate_new_coverage(line, [line]) is None


def test_partial_overlap_keeps_only_uncovered_geometry():
    original = LineString([(0, 0), (1, 0)])
    extension = LineString([(0, 0), (2, 0)])
    new = calculate_new_coverage(extension, [original])
    assert new is not None
    assert new.length < extension.length
