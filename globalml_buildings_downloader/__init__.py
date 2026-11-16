def classFactory(iface):
    from .plugin import GlobalMLBuildingsPlugin

    return GlobalMLBuildingsPlugin(iface)
