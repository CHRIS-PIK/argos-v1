from app.collectors.generic import collect_current


def collect() -> None:
    collect_current(
        collector_name="switches",
        endpoint="network-monitoring/v1/switches",
        table="switch_current",
        id_fields=("id", "serialNumber", "macAddress"),
        row_filter=lambda x: x.get("siteName") != "Onboarding",
    )
