import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsRectangle,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType
from qgis.PyQt.QtGui import QIcon

from . import index, quadkey, tiles
from .style import height_style

ICON = os.path.join(os.path.dirname(__file__), 'icon.svg')
WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')
POLYGONS, POINTS, BOTH = 0, 1, 2
LICENCE = 'CDLA Permissive 2.0 (https://cdla.dev/permissive-2-0/)'


def cache_dir():
    return os.path.join(
        QgsApplication.qgisSettingsDirPath(), 'cache', 'globalml_buildings'
    )


def tr(text):
    return QCoreApplication.translate('GlobalMLBuildings', text)


def _size(n_bytes):
    if n_bytes < 1e5:
        return '{} KB'.format(max(1, round(n_bytes / 1e3)))
    return '{:.1f} MB'.format(n_bytes / 1e6)


class DownloadBuildings(QgsProcessingAlgorithm):
    EXTENT = 'EXTENT'
    AREA = 'AREA'
    GEOMETRY = 'GEOMETRY'
    MAX_DOWNLOAD_MB = 'MAX_DOWNLOAD_MB'
    INDEX_URL = 'INDEX_URL'
    OUTPUT_POLYGONS = 'OUTPUT_POLYGONS'
    OUTPUT_POINTS = 'OUTPUT_POINTS'

    def name(self):
        return 'download'

    def displayName(self):
        return tr('Download buildings')

    def createInstance(self):
        return DownloadBuildings()

    def icon(self):
        return QIcon(ICON)

    def shortHelpString(self):
        return tr(
            'Downloads building footprints from Microsoft Global ML Building '
            'Footprints, release {}. Coverage is worldwide, with gaps.\n\n'
            'Area: the extent, or the polygons of a layer. When polygons are '
            'set they are used and the extent is ignored. A building is kept '
            'when its centroid falls inside the area.\n\n'
            'Microsoft publishes whole tiles (Bing zoom-9 quadkeys, about '
            '78 km across at the equator and narrower toward the poles), one '
            'file per country or region, so the first run in a region '
            'downloads every file the area touches. Files are cached in the '
            'QGIS profile folder and reused afterwards.\n\n'
            'Height is in metres. Height and confidence are empty where '
            'Microsoft has no value; for confidence that is every file '
            'sampled so far. Loaded layers are coloured by height: under '
            '6 m, 6 to 12 m, 12 to 25 m, 25 to 50 m, 50 m and over, and '
            'grey for no height.\n\n'
            'Data: Microsoft Global ML Building Footprints, {}. Credit '
            'Microsoft Global ML Building Footprints and the release date '
            'when you publish results. This plugin is not affiliated with '
            'Microsoft.'
        ).format(index.release(index.INDEX_URL), LICENCE)

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, tr('Extent'), optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.AREA,
                tr('Area polygons (overrides the extent)'),
                [QgsProcessing.SourceType.TypeVectorPolygon],
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.GEOMETRY,
                tr('Download as'),
                [tr('Polygons'), tr('Points'), tr('Polygons and points')],
                defaultValue=POLYGONS,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_DOWNLOAD_MB,
                tr('Stop if new downloads exceed (MB)'),
                QgsProcessingParameterNumber.Type.Integer,
                2000,
                minValue=1,
            )
        )
        index_url = QgsProcessingParameterString(
            self.INDEX_URL,
            tr('Index of tiles (dataset-links.csv URL)'),
            defaultValue=index.INDEX_URL,
        )
        index_url.setFlags(
            index_url.flags() | Qgis.ProcessingParameterFlag.Advanced
        )
        self.addParameter(index_url)
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POLYGONS,
                tr('Building polygons'),
                QgsProcessing.SourceType.TypeVectorPolygon,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POINTS,
                tr('Building points'),
                QgsProcessing.SourceType.TypeVectorPoint,
                optional=True,
            )
        )

    def checkParameterValues(self, parameters, context):
        if not parameters.get(self.AREA) and not parameters.get(self.EXTENT):
            return False, tr('Set an extent or a polygon layer.')
        return super().checkParameterValues(parameters, context)

    def _area(self, parameters, context):
        """The area in EPSG:4326, and whether it is a plain rectangle."""
        source = self.parameterAsSource(parameters, self.AREA, context)
        if source is None:
            geom = self.parameterAsExtentGeometry(
                parameters, self.EXTENT, context, WGS84
            )
            return geom, True
        transform = QgsCoordinateTransform(
            source.sourceCrs(), WGS84, context.transformContext()
        )
        parts = []
        for f in source.getFeatures():
            g = f.geometry()
            if g.isEmpty():
                continue
            g.transform(transform)
            parts.append(g)
        if not parts:
            raise QgsProcessingException(tr('The area layer has no polygons.'))
        return QgsGeometry.unaryUnion(parts), False

    def _index(self, url, cache, feedback):
        """(release, tiles by quadkey), or None when canceled."""
        try:
            release = index.release(url)
        except index.BadIndex:
            raise QgsProcessingException(
                tr(
                    'Cannot tell the release from the index URL {}. It '
                    'should end in /<release>/dataset-links.csv.'
                ).format(url)
            )
        path = index.cache_path(cache, release)
        feedback.pushInfo(
            tr('Microsoft Global ML Building Footprints, release {}').format(
                release
            )
        )
        if os.path.exists(path):
            feedback.pushInfo(tr('Index: cached'))
        else:
            feedback.pushInfo(tr('Index: downloading {}').format(url))
        try:
            tiles.download(
                url, path, lambda done, total: None, feedback.isCanceled
            )
        except tiles.Canceled:
            return None
        except tiles.DownloadError as e:
            raise QgsProcessingException(
                tr('Cannot reach the Microsoft building index: {}').format(e)
            )
        with open(path, encoding='utf-8') as f:
            text = f.read()
        try:
            return release, index.parse(text)
        except index.BadIndex as e:
            # Drop it so the next run fetches it again.
            os.remove(path)
            raise QgsProcessingException(
                tr('The index at {} is not a building index ({}).').format(
                    url, e
                )
            )

    def _quadkeys(self, area):
        bbox = area.boundingBox()
        found = []
        for qk in quadkey.tiles_in_bbox(
            bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()
        ):
            outline = QgsGeometry.fromRect(QgsRectangle(*quadkey.bounds(qk)))
            if outline.intersects(area):
                found.append(qk)
        return found

    def processAlgorithm(self, parameters, context, feedback):
        area, is_rect = self._area(parameters, context)
        mode = self.parameterAsEnum(parameters, self.GEOMETRY, context)
        max_bytes = (
            self.parameterAsInt(parameters, self.MAX_DOWNLOAD_MB, context)
            * 1e6
        )
        index_url = self.parameterAsString(
            parameters, self.INDEX_URL, context
        ).strip() or index.INDEX_URL
        cache = cache_dir()

        loaded = self._index(index_url, cache, feedback)
        if loaded is None:
            return {}
        release, by_quadkey = loaded
        quadkeys = self._quadkeys(area)
        feedback.pushInfo(
            tr('Area touches {} tile(s). Cache: {}').format(
                len(quadkeys), cache
            )
        )
        todo, new_bytes = [], 0
        for qk in quadkeys:
            found = by_quadkey.get(qk, [])
            if not found:
                feedback.pushInfo(tr('Tile {}: no buildings').format(qk))
            for tile in found:
                if os.path.exists(tiles.cache_path(cache, release, tile)):
                    feedback.pushInfo(
                        tr('Tile {} ({}): cached').format(qk, tile.region)
                    )
                else:
                    feedback.pushInfo(
                        tr('Tile {} ({}): {} to download').format(
                            qk, tile.region, _size(tile.size_bytes)
                        )
                    )
                    new_bytes += tile.size_bytes
                todo.append(tile)
        if not todo:
            raise QgsProcessingException(
                tr(
                    'Microsoft has no buildings here: no tile in the {} '
                    'release covers the area.'
                ).format(release)
            )
        if new_bytes > max_bytes:
            raise QgsProcessingException(
                tr(
                    'This area needs {:.0f} MB of new downloads, over the '
                    '{:.0f} MB limit. Use a smaller area or raise the limit.'
                ).format(new_bytes / 1e6, max_bytes / 1e6)
            )

        fields = QgsFields()
        fields.append(QgsField('height', QMetaType.Type.Double))
        fields.append(QgsField('confidence', QMetaType.Type.Double))
        fields.append(QgsField('area_in_meters', QMetaType.Type.Double))
        fields.append(QgsField('region', QMetaType.Type.QString))
        fields.append(QgsField('quadkey', QMetaType.Type.QString))
        results = {}
        poly_sink = point_sink = None
        if mode in (POLYGONS, BOTH):
            poly_sink, results[self.OUTPUT_POLYGONS] = self.parameterAsSink(
                parameters,
                self.OUTPUT_POLYGONS,
                context,
                fields,
                Qgis.WkbType.Polygon,
                WGS84,
            )
            if poly_sink is None:
                raise QgsProcessingException(
                    tr('Set the building polygons output.')
                )
        if mode in (POINTS, BOTH):
            point_sink, results[self.OUTPUT_POINTS] = self.parameterAsSink(
                parameters,
                self.OUTPUT_POINTS,
                context,
                fields,
                Qgis.WkbType.Point,
                WGS84,
            )
            if point_sink is None:
                raise QgsProcessingException(
                    tr('Set the building points output.')
                )
        for dest in results.values():
            if context.willLoadLayerOnCompletion(dest):
                context.layerToLoadOnCompletionDetails(dest).setPostProcessor(
                    height_style()
                )

        bbox = area.boundingBox()
        xmin, ymin, xmax, ymax = (
            bbox.xMinimum(),
            bbox.yMinimum(),
            bbox.xMaximum(),
            bbox.yMaximum(),
        )
        engine = None
        if not is_rect:
            engine = QgsGeometry.createGeometryEngine(area.constGet())
            engine.prepareGeometry()
        measure = QgsDistanceArea()
        measure.setSourceCrs(WGS84, context.transformContext())
        measure.setEllipsoid(WGS84.ellipsoidAcronym())
        fast = QgsFeatureSink.Flag.FastInsert
        kept = skipped = 0
        step = 100.0 / len(todo)

        for n, tile in enumerate(todo):
            base = n * step
            name = '{} ({})'.format(tile.quadkey, tile.region)

            def on_download(done, total):
                if total:
                    feedback.setProgress(base + step * 0.5 * done / total)

            def on_read(fraction):
                feedback.setProgress(base + step * (0.5 + 0.5 * fraction))

            feedback.setProgressText(
                tr('Tile {} of {}: {}').format(n + 1, len(todo), name)
            )
            try:
                path = tiles.download(
                    tile.url,
                    tiles.cache_path(cache, release, tile),
                    on_download,
                    feedback.isCanceled,
                )
            except tiles.Canceled:
                return {}
            except tiles.DownloadError as e:
                raise QgsProcessingException(
                    tr('Download failed: {}').format(e)
                )
            tile_kept = 0
            try:
                for kind, coords, height, conf in tiles.features(
                    path, on_read
                ):
                    if feedback.isCanceled():
                        return {}
                    if kind != 'Polygon' or not coords or not coords[0]:
                        skipped += 1
                        continue
                    # A centroid lies inside the outer ring's bounding box,
                    # so this skips most of a tile without building geometry.
                    xs = [p[0] for p in coords[0]]
                    ys = [p[1] for p in coords[0]]
                    if (
                        min(xs) > xmax
                        or max(xs) < xmin
                        or min(ys) > ymax
                        or max(ys) < ymin
                    ):
                        continue
                    polygon = QgsGeometry.fromPolygonXY(
                        [[QgsPointXY(p[0], p[1]) for p in ring]
                         for ring in coords]
                    )
                    centroid = polygon.centroid()
                    c = centroid.asPoint()
                    if not (xmin <= c.x() <= xmax and ymin <= c.y() <= ymax):
                        continue
                    if engine is not None and not engine.contains(
                        centroid.constGet()
                    ):
                        continue
                    attrs = [
                        height,
                        conf,
                        round(measure.measureArea(polygon), 2),
                        tile.region,
                        tile.quadkey,
                    ]
                    if poly_sink is not None:
                        f = QgsFeature(fields)
                        f.setGeometry(polygon)
                        f.setAttributes(attrs)
                        poly_sink.addFeature(f, fast)
                    if point_sink is not None:
                        f = QgsFeature(fields)
                        f.setGeometry(centroid)
                        f.setAttributes(attrs)
                        point_sink.addFeature(f, fast)
                    tile_kept += 1
            except (OSError, EOFError, ValueError) as e:
                raise QgsProcessingException(
                    tr(
                        'Cannot read the cached tile {}: {}. Delete the file '
                        'and run again.'
                    ).format(path, e)
                )
            feedback.pushInfo(
                tr('Tile {}: {} building(s) kept').format(name, tile_kept)
            )
            kept += tile_kept

        feedback.pushInfo(
            tr('Skipped {} feature(s) that are not polygons').format(skipped)
        )
        feedback.pushInfo(tr('{} building(s) in total').format(kept))
        feedback.pushInfo(
            tr(
                'Data: Microsoft Global ML Building Footprints, release {}, '
                '{}.'
            ).format(release, LICENCE)
        )
        results['COUNT'] = kept
        return results
