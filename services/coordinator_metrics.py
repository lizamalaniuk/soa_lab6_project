from prometheus_client import Counter, Histogram, start_http_server

SAGA_MESSAGES = Counter(
    "saga_coordinator_messages_total",
    "Messages handled by Saga Coordinator",
    ["result"]
)

SAGA_DURATION = Histogram(
    "saga_coordinator_duration_seconds",
    "Saga message processing duration",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, float("inf"))
)


def start_metrics():
    start_http_server(9101, addr="0.0.0.0")
