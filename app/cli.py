from __future__ import annotations
import argparse
from app.collectors.aps import collect as collect_aps
from app.collectors.clients import collect as collect_clients
from app.collectors.switches import collect as collect_switches
from app.collectors.radios import collect as collect_radios
from app.collectors.alerts import collect as collect_alerts
from app.collectors.licenses import collect as collect_licenses
from app.collectors.insights import collect as collect_insights
from app.retention import cleanup

COMMANDS = {
    "aps": collect_aps,
    "clients": collect_clients,
    "switches": collect_switches,
    "radios": collect_radios,
    "alerts": collect_alerts,
    "licenses": collect_licenses,
    "insights": collect_insights,
    "cleanup": cleanup,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
