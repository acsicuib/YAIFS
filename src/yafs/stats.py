from yafs.metrics import Metrics, MetricsAnalyzer


class Stats(MetricsAnalyzer):
    """
    Backward-compatible metrics reader.

    ``Stats`` now delegates to :class:`yafs.metrics.MetricsAnalyzer`, keeping
    the historical API while exposing richer analysis helpers from the new
    metrics layer.
    """

    def __init__(self, defaultPath: str = "result", app_definition=None):
        super().__init__(defaultPath=defaultPath, app_definition=app_definition)


__all__ = ["Metrics", "MetricsAnalyzer", "Stats"]
