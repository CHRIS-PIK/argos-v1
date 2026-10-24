from __future__ import annotations

import atexit
import logging
import os

import pyroscope
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialized = False
_tracer_provider: TracerProvider | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_observability(service_name: str) -> None:
    global _initialized, _tracer_provider

    if _initialized:
        return

    environment = os.getenv("APP_ENVIRONMENT", "homelab")
    host_name = os.getenv("HOST_NAME", "olympus")
    otlp_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://host.docker.internal:4317",
    )
    pyroscope_endpoint = os.getenv(
        "PYROSCOPE_SERVER_ADDRESS",
        "http://host.docker.internal:4040",
    )

    resource = Resource.create(
        {
            "service.name": f"argos-{service_name}",
            "service.namespace": "argos",
            "deployment.environment.name": environment,
            "host.name": host_name,
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=otlp_endpoint,
                insecure=True,
            )
        )
    )
    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    atexit.register(provider.shutdown)

    RequestsInstrumentor().instrument()
    URLLib3Instrumentor().instrument()
    ThreadingInstrumentor().instrument()

    try:
        pyroscope.configure(
            application_name=f"argos.{service_name}",
            server_address=pyroscope_endpoint,
            sample_rate=max(1, int(os.getenv("PYROSCOPE_SAMPLE_RATE", "100"))),
            cpu_enabled=True,
            oncpu=True,
            gil_only=True,
            mem_enabled=_env_bool("PYROSCOPE_MEMORY_ENABLED", True),
            enable_logging=True,
            tags={
                "service": service_name,
                "application": "argos",
                "environment": environment,
                "host": host_name,
            },
        )
    except Exception:
        logger.exception("failed to initialize Pyroscope")

    _initialized = True
