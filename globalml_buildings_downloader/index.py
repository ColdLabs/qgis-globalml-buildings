"""Parse the Microsoft Global ML Building Footprints index, dataset-links.csv.

Pure Python so it can be tested without QGIS."""

import csv
import io
import os
import posixpath
import re
from collections import namedtuple
from urllib.parse import unquote, urlparse

# Microsoft publishes no stable "latest" link, so the plugin pins a release.
INDEX_URL = (
    'https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv'
)
FILE_NAME = 'dataset-links.csv'
COLUMNS = ('Location', 'QuadKey', 'Url', 'Size')

Tile = namedtuple('Tile', 'region quadkey url size_bytes')

# The index writes sizes in binary units: 979.4KB is a 1,002,933-byte file.
_UNITS = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
_SIZE = re.compile(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([KMG]?B)\s*')
# Release and region names become cache folder names.
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
_QUADKEY = re.compile(r'[0-3]{1,23}')


class BadIndex(ValueError):
    pass


def parse_size(text):
    """Bytes in a size such as 979.4KB, 27.8MB or 1.2GB."""
    m = _SIZE.fullmatch(text)
    if not m:
        raise BadIndex('unreadable size %r' % text)
    return round(float(m.group(1)) * _UNITS[m.group(2)])


def release(url):
    """The release folder in an index URL, e.g. 2026-08-13."""
    name = unquote(posixpath.basename(posixpath.dirname(urlparse(url).path)))
    if not _NAME.fullmatch(name):
        raise BadIndex('no release folder in %s' % url)
    return name


def cache_path(cache_dir, release_name):
    return os.path.join(cache_dir, release_name, FILE_NAME)


def parse(text):
    """Tiles by quadkey. A quadkey on a border has one tile per region."""
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise BadIndex('missing column(s) %s' % ', '.join(missing))
    by_quadkey = {}
    for row in reader:
        region, quadkey = row['Location'], row['QuadKey']
        if not _NAME.fullmatch(region or ''):
            raise BadIndex('bad region name %r' % region)
        if not _QUADKEY.fullmatch(quadkey or ''):
            raise BadIndex('bad quadkey %r' % quadkey)
        tile = Tile(region, quadkey, row['Url'], parse_size(row['Size']))
        by_quadkey.setdefault(quadkey, []).append(tile)
    return by_quadkey
