from __future__ import annotations
import argparse
from app.collectors.aps import collect as collect_aps
from app.collectors.clients import collect as collect_clients
from app.retention import cleanup

COMMANDS = {"aps": collect_aps, "clients": collect_clients, "cleanup": cleanup}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    COMMANDS[args.command]()

if __name__ == "__main__":
    main()
