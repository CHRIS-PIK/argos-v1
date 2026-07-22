from app.collectors.generic import collect_current


def collect() -> None:
    collect_current(
        collector_name="alerts",
        endpoint="network-notifications/v1/alerts",
        table="alert_current",
        id_fields=("id", "alertId", "uuid"),
    )
