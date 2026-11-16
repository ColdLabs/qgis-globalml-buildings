import pytest

from globalml_buildings_downloader import quadkey


def test_point_in_minho_valley():
    assert quadkey.tiles_in_bbox(-8.4392, 42.0702, -8.4392, 42.0702) == [
        '031332213'
    ]


def test_bing_docs_example():
    # Bing Maps Tile System docs: tile x=3, y=5 at level 3 is "213".
    assert quadkey.from_tile(3, 5, 3) == '213'
    assert quadkey.to_tile('213') == (3, 5, 3)


def test_bounds_of_bing_example():
    xmin, ymin, xmax, ymax = quadkey.bounds('213')
    assert (xmin, xmax) == (-45.0, 0.0)
    assert ymin == pytest.approx(-66.51326, abs=1e-5)
    assert ymax == pytest.approx(-40.97990, abs=1e-5)


def test_bounds_contain_the_point_that_named_them():
    xmin, ymin, xmax, ymax = quadkey.bounds('031332213')
    assert xmin <= -8.4392 <= xmax
    assert ymin <= 42.0702 <= ymax
    assert xmax - xmin == pytest.approx(360 / 512)


def test_tile_centre_round_trips():
    for qk in ['031332213', '120210233', '300000000', '033333333']:
        xmin, ymin, xmax, ymax = quadkey.bounds(qk)
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        assert quadkey.tiles_in_bbox(cx, cy, cx, cy) == [qk]


def test_bbox_over_four_tiles_lists_each_once():
    xmin, ymin, xmax, ymax = quadkey.bounds('031332213')
    got = quadkey.tiles_in_bbox(xmax - 0.01, ymin - 0.01, xmax + 0.01, ymin + 0.01)
    assert len(got) == 4
    assert len(set(got)) == 4
    assert '031332213' in got


def test_poles_clamp_to_the_last_row():
    north = quadkey.tiles_in_bbox(0.1, 89.9, 0.1, 89.9)
    south = quadkey.tiles_in_bbox(0.1, -89.9, 0.1, -89.9)
    assert quadkey.to_tile(north[0])[1] == 0
    assert quadkey.to_tile(south[0])[1] == 511


def test_dateline_stays_in_range():
    assert quadkey.to_tile(quadkey.tiles_in_bbox(180, 0, 180, 0)[0])[0] == 511
    assert quadkey.to_tile(quadkey.tiles_in_bbox(-180, 0, -180, 0)[0])[0] == 0
