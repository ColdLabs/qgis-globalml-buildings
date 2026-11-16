import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithm import DownloadBuildings


class Provider(QgsProcessingProvider):
    def id(self):
        return 'globalmlbuildings'

    def name(self):
        return 'Microsoft Global ML Buildings'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icon.svg'))

    def loadAlgorithms(self):
        self.addAlgorithm(DownloadBuildings())
