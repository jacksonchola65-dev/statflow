from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "statflow_http_requests_total",
    "Total HTTP requests.",
    ("method", "route", "status_code"),
)
HTTP_REQUEST_DURATION = Histogram(
    "statflow_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
READINESS = Gauge(
    "statflow_readiness",
    "Whether the application readiness probe most recently succeeded.",
)
READINESS.set(0)


def route_template(request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and template else "unknown"
