#!/usr/bin/env bash
# Importa (ou atualiza) o dashboard do Argos em um Grafana.
#
# Uso:
#   GRAFANA_URL=http://192.168.0.121:3000 GRAFANA_TOKEN=<token> ./scripts/grafana-import.sh
#   ./scripts/grafana-import.sh --dry-run          # só monta o payload, sem chamar o Grafana
#
# O token é lido da variável de ambiente e nunca é impresso. Crie uma service account
# com papel Editor (Administration > Users and access > Service accounts) e REVOGUE o
# token depois de importar. Variáveis opcionais: GRAFANA_FOLDER_UID (pasta de destino).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD="$ROOT/grafana/dashboards/argos-overview.json"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

[[ -f "$DASHBOARD" ]] || { echo "[ERRO] não achei $DASHBOARD" >&2; exit 1; }

PAYLOAD="$(python3 - "$DASHBOARD" "${GRAFANA_FOLDER_UID:-}" <<'PY'
import json, sys

dashboard = json.load(open(sys.argv[1], encoding="utf-8"))
dashboard["id"] = None
payload = {"dashboard": dashboard, "overwrite": True, "message": "Importado por scripts/grafana-import.sh"}
if sys.argv[2]:
    payload["folderUid"] = sys.argv[2]
print(json.dumps(payload))
PY
)"

if $DRY_RUN; then
    echo "payload ok: $(printf '%s' "$PAYLOAD" | wc -c) bytes, uid=argos-overview"
    exit 0
fi

: "${GRAFANA_URL:?defina GRAFANA_URL, ex.: http://192.168.0.121:3000}"
: "${GRAFANA_TOKEN:?defina GRAFANA_TOKEN (service account, papel Editor)}"

RESPONSE="$(printf '%s' "$PAYLOAD" | curl -fsS -X POST "${GRAFANA_URL%/}/api/dashboards/db" \
    -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
    -H "Content-Type: application/json" \
    --data-binary @-)"

echo "$RESPONSE" | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("dashboard:", r.get("status"), "|", r.get("url"))
'
