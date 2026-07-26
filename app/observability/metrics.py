from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

PRODUCER_CYCLES = Counter(
    "datalake_producer_cycles_total",
    "Total de ciclos executados pelo producer.",
    ["status"],
)
PRODUCER_PAGES_COLLECTED = Counter(
    "datalake_pages_collected_total",
    "Total de páginas válidas coletadas.",
    ["collector"],
)
PRODUCER_PAGES_QUEUED = Counter(
    "datalake_pages_queued_total",
    "Total de páginas inseridas na fila.",
    ["collector"],
)
PRODUCER_COLLECTION_DURATION = Histogram(
    "datalake_collection_duration_seconds",
    "Tempo de coleta de cada endpoint.",
    ["collector"],
)
PRODUCER_LAST_SUCCESS = Gauge(
    "datalake_last_success_timestamp_seconds",
    "Timestamp Unix da última coleta bem-sucedida.",
    ["collector"],
)
PRODUCER_PAGINATION_STOPS = Counter(
    "datalake_pagination_stops_total",
    "Total de interrupções preventivas de paginação.",
    ["collector", "reason"],
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

WORKER_MESSAGES = Counter(
    "datalake_messages_total",
    "Total de mensagens tratadas pelo worker.",
    ["collector", "status"],
)
WORKER_ITEMS_PROCESSED = Counter(
    "datalake_items_processed_total",
    "Total de itens processados pelo worker.",
    ["collector"],
)
WORKER_RECORDS_WRITTEN = Counter(
    "datalake_records_written_total",
    "Total de operações de escrita realizadas pelos processors.",
    ["collector"],
)
WORKER_PROCESSING_DURATION = Histogram(
    "datalake_processing_duration_seconds",
    "Tempo de processamento de uma mensagem da fila.",
    ["collector"],
)
WORKER_STALE_RECOVERED = Counter(
    "datalake_stale_messages_recovered_total",
    "Total de mensagens PROCESSING recuperadas após lock expirado.",
)

QUEUE_MESSAGES = Gauge(
    "datalake_queue_messages",
    "Quantidade atual de mensagens por status na ingestion_queue.",
    ["status"],
)
QUEUE_BACKLOG = Gauge(
    "datalake_queue_backlog",
    "Mensagens aguardando processamento, somando PENDING e FAILED.",
)
QUEUE_OLDEST_PENDING_AGE = Gauge(
    "datalake_queue_oldest_pending_age_seconds",
    "Idade em segundos da mensagem disponível mais antiga.",
)
