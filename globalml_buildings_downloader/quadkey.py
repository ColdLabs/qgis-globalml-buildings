"""Bing Maps tile quadkeys (Web Mercator), as used by the Microsoft index.

Pure Python so it can be tested without QGIS."""

import math

MAX_LAT = 85.05112878


def _tile_xy(lng, lat, zoom):
    n = 1 << zoom
    lat = min(max(lat, -MAX_LAT), MAX_LAT)
    s = math.sin(math.radians(lat))
    x = math.floor((lng + 180.0) / 360.0 * n)
    y = math.floor((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def from_tile(x, y, zoom):
    digits = []
    for i in range(zoom, 0, -1):
        mask = 1 << (i - 1)
        digits.append(str((1 if x & mask else 0) + (2 if y & mask else 0)))
    return ''.join(digits)


def to_tile(quadkey):
    x = y = 0
    zoom = len(quadkey)
    for i, digit in enumerate(quadkey):
        mask = 1 << (zoom - i - 1)
        d = int(digit)
        if d & 1:
            x |= mask
        if d & 2:
            y |= mask
    return x, y, zoom


def tiles_in_bbox(xmin, ymin, xmax, ymax, zoom=9):
    """Quadkeys of every tile the bounding box (degrees) touches."""
    x0, y0 = _tile_xy(xmin, ymax, zoom)
    x1, y1 = _tile_xy(xmax, ymin, zoom)
    return [
        from_tile(x, y, zoom)
        for y in range(y0, y1 + 1)
        for x in range(x0, x1 + 1)
    ]


def _lat(y, n):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def bounds(quadkey):
    """(xmin, ymin, xmax, ymax) of the tile, in degrees."""
    x, y, zoom = to_tile(quadkey)
    n = 1 << zoom
    return (
        x / n * 360.0 - 180.0,
        _lat(y + 1, n),
        (x + 1) / n * 360.0 - 180.0,
        _lat(y, n),
    )
