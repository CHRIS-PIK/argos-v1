# Piloto DataLake NS (Argos) → Power BI

Este piloto retira do Zabbix os payloads destinados a relatório e mantém o Zabbix apenas como monitor da saúde da esteira.

## Escopo inicial

- Renovação de token com `refresh_token` ou `client_credentials`.
- Coleta paginada de APs: `network-monitoring/v1/aps`.
- Coleta paginada de clientes: `network-monitoring/v1/clients`.
- Estado atual de APs e clientes via `upsert`.
- Histórico de métricas de APs a cada 10 minutos.
- Resumo de clientes por site, dispositivo, conexão, banda e WLAN a cada 10 minutos.
- Retenção automática de 90 dias.
- Views básicas para o Power BI.
- Registro de sucesso, falha, páginas e quantidade de registros por execução.

## Subida

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f ingestor
```

## Testes manuais

```bash
docker compose exec ingestor python -m app.cli aps
docker compose exec ingestor python -m app.cli clients
docker compose exec ingestor python -m app.cli cleanup
```

## Validação no banco

```sql
SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 20;
SELECT COUNT(*) FROM ap_current;
SELECT COUNT(*) FROM ap_metrics_10m;
SELECT COUNT(*) FROM client_current;
SELECT COUNT(*) FROM client_summary_10m;
```

## Conexão do Power BI

Conectar ao MariaDB usando um usuário somente leitura e consumir preferencialmente:

- `vw_ap_latest`
- `vw_client_summary`

Não usar o usuário `aruba_ingestor` no Power BI. Crie um usuário dedicado:

```sql
CREATE USER 'powerbi_reader'@'%' IDENTIFIED BY 'troque_esta_senha';
GRANT SELECT ON aruba_reporting.* TO 'powerbi_reader'@'%';
FLUSH PRIVILEGES;
```

## Critérios de aceite do piloto

1. Token é renovado sem edição manual por 24 horas.
2. Todas as páginas dos endpoints são percorridas.
3. APs e clientes de Onboarding são descartados.
4. Duas execuções no mesmo bucket de 10 minutos não duplicam métricas.
5. Power BI lê as views com um usuário somente leitura.
6. A tabela `ingestion_runs` deixa claro qualquer erro de autenticação, API ou banco.
7. Após validação, são adicionados rádios, switches, alertas, licenças e IA Insights.

## Observações para adequação à API real

A estrutura de resposta do template indica `body.items`/`items`, `next`, `total` e `count`. Na primeira execução, valide os nomes reais dos identificadores dos clientes e o formato exato do `next`. Os coletores guardam o JSON bruto no estado atual para facilitar esse ajuste sem perder evidências.
