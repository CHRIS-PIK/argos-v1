from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

COLLECTOR_CYCLES = Counter(
    "argos_collector_cycles_total",
    "Total de ciclos executados pelo coletor.",
    ["status"],
)
COLLECTOR_PAGES_COLLECTED = Counter(
    "argos_collector_pages_collected_total",
    "Total de páginas válidas coletadas.",
    ["event_type"],
)
COLLECTOR_BATCHES_SENT = Counter(
    "argos_collector_batches_sent_total",
    "Total de lotes enviados à plataforma, por resultado.",
    ["event_type", "result"],
)
COLLECTOR_COLLECTION_DURATION = Histogram(
    "argos_collector_collection_duration_seconds",
    "Tempo de coleta de cada endpoint.",
    ["event_type"],
)
COLLECTOR_LAST_SUCCESS = Gauge(
    "argos_collector_last_success_timestamp_seconds",
    "Timestamp Unix da última coleta bem-sucedida.",
    ["event_type"],
)
COLLECTOR_PAGINATION_STOPS = Counter(
    "argos_collector_pagination_stops_total",
    "Total de interrupções preventivas de paginação.",
    ["event_type", "reason"],
)

ARUBA_REQUESTS = Counter(
    "aruba_requests_total",
    "Total de requisições HTTP enviadas à API Aruba.",
    ["endpoint", "method", "status"],
)
ARUBA_REQUEST_ERRORS = Counter(
    "aruba_request_errors_total",
    "Total de erros ao acessar a API Aruba.",
    ["endpoint", "error_type"],
)
ARUBA_REQUEST_DURATION = Histogram(
    "aruba_request_duration_seconds",
    "Duração das requisições HTTP à API Aruba.",
    ["endpoint", "method"],
)
