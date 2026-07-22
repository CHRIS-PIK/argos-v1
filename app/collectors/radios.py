from app.collectors.generic import collect_current


def collect() -> None:
    collect_current(
        collector_name="radios",
        endpoint="network-monitoring/v1/radios",
        table="radio_current",
        id_fields=("id", "radioId", "macAddress"),
        row_filter=lambda x: x.get("siteName") != "Onboarding",
    )
