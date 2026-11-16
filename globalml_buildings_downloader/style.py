from qgis.core import (
    Qgis,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsProcessingLayerPostProcessorInterface,
    QgsRuleBasedRenderer,
)

# Height bands in metres (lower bound inclusive), roughly 1-2 floors, 3-4,
# 5-8, 9-16 and towers. Viridis colours, light for low and dark for tall.
BANDS = [
    ('"height" < 6', 'Under 6 m', '253,231,37'),
    ('"height" >= 6 AND "height" < 12', '6 to 12 m', '94,201,98'),
    ('"height" >= 12 AND "height" < 25', '12 to 25 m', '33,145,140'),
    ('"height" >= 25 AND "height" < 50', '25 to 50 m', '59,82,139'),
    ('"height" >= 50', '50 m and over', '68,1,84'),
    ('"height" IS NULL', 'No height', '158,158,158'),
]


def _symbol(geometry_type, rgb):
    if geometry_type == Qgis.GeometryType.Point:
        return QgsMarkerSymbol.createSimple(
            {
                'name': 'circle',
                'color': rgb,
                'size': '1.6',
                'outline_style': 'no',
            }
        )
    return QgsFillSymbol.createSimple(
        {'color': rgb + ',200', 'outline_color': rgb, 'outline_width': '0.2'}
    )


def height_renderer(geometry_type):
    root = QgsRuleBasedRenderer.Rule(None)
    for expression, label, rgb in BANDS:
        root.appendChild(
            QgsRuleBasedRenderer.Rule(
                _symbol(geometry_type, rgb), 0, 0, expression, label
            )
        )
    return QgsRuleBasedRenderer(root)


class HeightStyle(QgsProcessingLayerPostProcessorInterface):
    def postProcessLayer(self, layer, context, feedback):
        layer.setRenderer(height_renderer(layer.geometryType()))
        layer.triggerRepaint()


# QGIS takes ownership of a post-processor and deletes it after the run, so
# every output of every run needs a new one. Python still holds each one, or
# the wrapper could be collected before QGIS calls it.
_live = []


def height_style():
    style = HeightStyle()
    _live.append(style)
    return style
