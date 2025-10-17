import os
import threading

import staticconf

_clusterman_metrics_lock = threading.Lock()

_clusterman_metrics_loaded = False

CLUSTERMAN_YAML_FILE_PATH = "/nail/srv/configs/clusterman.yaml"
CLUSTERMAN_METRICS_YAML_FILE_PATH = "/nail/srv/configs/clusterman_metrics.yaml"


def get_clusterman_metrics():
    try:
        import clusterman_metrics
        import clusterman_metrics.util.costs

        clusterman_yaml = CLUSTERMAN_YAML_FILE_PATH
        _ensure_metrics_configuration()
    except (ImportError, FileNotFoundError):
        # our cluster autoscaler is not currently open source, sorry!
        clusterman_metrics = None
        clusterman_yaml = None

    return clusterman_metrics, clusterman_yaml


def _ensure_metrics_configuration() -> None:
    global _clusterman_metrics_loaded, _clusterman_metrics_signature

    path = CLUSTERMAN_METRICS_YAML_FILE_PATH
    with _clusterman_metrics_lock:
        stat_result = os.stat(path)
        mtime_ns = getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000))
        current_signature = (mtime_ns, stat_result.st_size)
        if not _clusterman_metrics_loaded or current_signature != _clusterman_metrics_signature:
            staticconf.YamlConfiguration(path, namespace="clusterman_metrics")
            _clusterman_metrics_loaded = True
            _clusterman_metrics_signature = current_signature
