"""
Dependency-free Prometheus-style metrics registry.

Provides counters, gauges and histograms and renders them in the Prometheus
text exposition format (https://prometheus.io/docs/instrumenting/exposition_formats/).
Only the standard library is used, so enabling /metrics never pulls additional
runtime dependencies and stays deterministic for tests.

Thread-safety: every mutation and the render pass hold a single lock, which is
plenty for an API of this size.
"""

import threading

# Default histogram buckets (seconds) covering realistic request latencies.
DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _label_key(labels):
    """Canonical label key: an ordered tuple of (name, value) pairs."""
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


def _escape_label_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_sample(name, label_key, value):
    """One exposition line: name{labels} value (labels optional)."""
    if not label_key:
        return f"{name} {value:g}"
    labels = ",".join(
        f'{k}="{_escape_label_value(v)}"' for k, v in label_key
    )
    return f'{name}{{{labels}}} {value:g}'


class Metrics:
    """Tiny registry: counters, gauges, histograms + a Prometheus renderer."""

    def __init__(self):
        self._lock = threading.Lock()
        self._default_buckets = list(DEFAULT_BUCKETS)
        # name -> help text (kept as declared at registration time)
        self._help = {}
        # (name, label_key) -> float
        self._counters = {}
        self._gauges = {}
        # name -> {"buckets": [...], "series": {label_key: {"cumulative": [...], "sum": float, "count": float}}}
        self._histograms = {}

    def reset(self):
        """Drop every recorded sample (used by tests)."""
        with self._lock:
            self._help.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def inc(self, name, help_text="", labels=None, amount=1.0):
        """Increment a counter by *amount* under *labels*."""
        key = (name, _label_key(labels))
        with self._lock:
            if name not in self._help:
                self._help[name] = help_text
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def gauge(self, name, help_text="", value=0.0, labels=None):
        """Set a gauge to *value* under *labels*."""
        key = (name, _label_key(labels))
        with self._lock:
            if name not in self._help:
                self._help[name] = help_text
            self._gauges[key] = float(value)

    def observe(self, name, value, help_text="", labels=None, buckets=None):
        """Record one observation into an exponential-style histogram."""
        with self._lock:
            if name not in self._help:
                self._help[name] = help_text
            bounds = list(buckets or self._default_buckets)
            hist = self._histograms.setdefault(
                name, {"buckets": bounds, "series": {}}
            )
            key = _label_key(labels)
            series = hist["series"].get(key)
            if series is None:
                series = {
                    "cumulative": [0.0] * (len(bounds) + 1),
                    "sum": 0.0,
                    "count": 0.0,
                }
                hist["series"][key] = series
            series["sum"] += value
            series["count"] += 1.0
            for i, bound in enumerate(bounds):
                if value <= bound:
                    series["cumulative"][i] += 1.0
            series["cumulative"][-1] += 1.0

    def render(self) -> str:
        """Exposition text for every registered metric, sorted for stability."""
        lines = []
        with self._lock:
            # --- counters ----------------------------------------------------
            names = sorted({name for name, _ in self._counters})
            for name in names:
                help_text = self._help.get(name, "")
                if help_text:
                    lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                for key, value in sorted(
                    (k, v) for k, v in self._counters.items() if k[0] == name
                ):
                    lines.append(_format_sample(name, key[1], value))

            # --- gauges ------------------------------------------------------
            for name in sorted({name for name, _ in self._gauges}):
                help_text = self._help.get(name, "")
                if help_text:
                    lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
                for key, value in sorted(
                    (k, v) for k, v in self._gauges.items() if k[0] == name
                ):
                    lines.append(_format_sample(name, key[1], value))

            # --- histograms ----------------------------------------------------
            for name in sorted(self._histograms):
                help_text = self._help.get(name, "")
                if help_text:
                    lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} histogram")
                hist = self._histograms[name]
                bounds = hist["buckets"]
                for label_key in sorted(hist["series"]):
                    series = hist["series"][label_key]
                    for i in range(len(bounds) + 1):
                        bound = "+Inf" if i == len(bounds) else bounds[i]
                        lines.append(
                            _format_sample(
                                f"{name}_bucket",
                                label_key + (("le", bound),),
                                series["cumulative"][i],
                            )
                        )
                    lines.append(_format_sample(f"{name}_sum", label_key, series["sum"]))
                    lines.append(_format_sample(f"{name}_count", label_key, series["count"]))

        return "\n".join(lines) + ("\n" if lines else "")


# App-wide singleton used by app/main.py.
metrics = Metrics()