from app.collectors.generic import collect_current


def collect() -> None:
    collect_current(
        collector_name="licenses",
        endpoint="platform/licensing/v1/subscriptions",
        table="license_current",
        id_fields=("id", "subscriptionId", "licenseId", "key"),
    )
