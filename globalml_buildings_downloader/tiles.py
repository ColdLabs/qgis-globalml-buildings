"""Fetch and read Microsoft Global ML Building Footprints tiles.

One gzipped file of line-delimited GeoJSON features per region and Bing
zoom-9 quadkey, in EPSG:4326."""

import gzip
import json
import os

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QEventLoop, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest


class Canceled(Exception):
    pass


class DownloadError(Exception):
    pass


def cache_path(cache_dir, release, tile):
    return os.path.join(
        cache_dir, release, tile.region, tile.quadkey + '.geojsonl.gz'
    )


def _request(url):
    # Tiles are cached on disk by the plugin; keep them out of QGIS's own
    # network cache, which is far too small for them.
    req = QNetworkRequest(QUrl(url))
    req.setAttribute(
        QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QNetworkRequest.CacheLoadControl.AlwaysNetwork,
    )
    req.setAttribute(
        QNetworkRequest.Attribute.CacheSaveControlAttribute, False
    )
    return req


def download(url, path, on_progress, is_canceled):
    """Download url to path unless path exists; return path.

    Goes through QGIS's network manager, so proxy and SSL settings apply, and
    streams to a .part file renamed at the end, so an interrupted download
    never leaves a truncated file behind."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + '.part'
    with open(part, 'wb') as out:
        reply = QgsNetworkAccessManager.instance().get(_request(url))
        loop = QEventLoop()

        def drain():
            if reply.isOpen():
                out.write(reply.readAll().data())

        def check_canceled():
            if is_canceled():
                reply.abort()

        reply.readyRead.connect(drain)
        reply.downloadProgress.connect(
            lambda done, total: on_progress(done, total if total > 0 else None)
        )
        reply.finished.connect(loop.quit)
        poll = QTimer()
        poll.timeout.connect(check_canceled)
        poll.start(250)
        loop.exec()
        poll.stop()
        drain()
        error, message = reply.error(), reply.errorString()
        reply.deleteLater()
    if is_canceled():
        os.remove(part)
        raise Canceled()
    if error != QNetworkReply.NetworkError.NoError:
        os.remove(part)
        raise DownloadError('%s: %s' % (url, message))
    os.replace(part, path)
    return path


def _known(value):
    # Microsoft writes -1 where it has no value.
    return value if value is not None and value >= 0 else None


def features(path, on_progress):
    """Yield (geometry type, coordinates, height, confidence) per building,
    reporting the share of the file read. Unknown values come back as None."""
    size = os.path.getsize(path) or 1
    with open(path, 'rb') as raw, gzip.open(raw, 'rt', encoding='utf-8') as f:
        for n, line in enumerate(f):
            if n % 20000 == 0:
                on_progress(raw.tell() / size)
            if not line.strip():
                continue
            feature = json.loads(line)
            geometry = feature.get('geometry') or {}
            props = feature.get('properties') or {}
            yield (
                geometry.get('type'),
                geometry.get('coordinates'),
                _known(props.get('height')),
                _known(props.get('confidence')),
            )
