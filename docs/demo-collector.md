# Coletor de demonstração (APIs públicas)

`collectors/public-demo` busca duas APIs públicas, sem cadastro nem chave, e envia à Ingest API. Serve para testar a plataforma de ponta a ponta com dados que não têm nada a ver com a Aruba e como exemplo mínimo de um coletor novo.

| Job | Fonte | `source` / `event_type` | O que mostra |
|---|---|---|---|
| `usgs` | [USGS Earthquakes](https://earthquake.usgs.gov/earthquakes/feed/) (GeoJSON das últimas 24 h) | `usgs` / `earthquakes` | Formato diferente (GeoJSON, id no topo, campos aninhados em `properties.*`). O mesmo terremoto muda de `automatic` para `reviewed`, o que gera histórico. |
| `openmeteo` | [Open-Meteo](https://open-meteo.com/) (clima atual de 14 capitais) | `open-meteo` / `weather` | Série temporal: o mesmo id muda a cada janela de 10 min. `status` é a condição do tempo (chuva, nublado…). |

## Subindo

1. Crie uma chave de coletor restrita a esses dois tipos:

```bash
docker compose exec ingest python -m app.ingest.keys create --name demo --tenant default --role collector --event-types earthquakes,weather
```

2. Configure e suba (o serviço está no profile `demo` e não sobe junto com o resto):

```bash
cp collectors/public-demo/.env.example collectors/public-demo/.env
# edite ARGOS_API_KEY com a chave criada acima
docker compose --profile demo up -d --build collector-demo
docker compose logs -f collector-demo
```

3. Para o worker e a Query API enxergarem os tipos novos, reinicie-os (eles carregam os schemas na partida):

```bash
docker compose restart ingest worker query
```

O compose já monta `collectors/public-demo/schemas` em `/schemas/public-demo` nesses três serviços.

Cada ciclo (padrão: 5 minutos) deve logar `job=earthquakes items=… batches_new=…` e `job=weather items=14 …`. Na interface (`http://<host>:8090`), os tipos `earthquakes` e `weather` aparecem nos filtros de tipo.

## O que olhar na interface

- **Entidades › tipo `weather`:** 14 cidades. Filtre pela dimensão `region` (Sudeste, Sul…) e por status (`chuva`, `nublado`…).
- **Entidades › tipo `earthquakes`:** filtre por dimensão `magnitude` ou `type`; abra um terremoto para ver o payload GeoJSON completo.
- **Eventos › `weather`, últimos 24 h:** uma linha por cidade a cada janela de 10 minutos.
- **Exportar** com “dimensões como colunas” (`region`, `state`) em XLSX ou Parquet.
- **Fontes e fila** (chave admin): `usgs` e `open-meteo` com “em dia”.

## Como o mapeamento é feito

Os schemas em `collectors/public-demo/schemas/` usam caminhos aninhados no bloco `x-argos`, por exemplo no terremoto:

```json
"x-argos": {
  "entity_id": ["id"],
  "name": ["properties.place"],
  "status": ["properties.status"],
  "dimensions": { "type": "properties.type", "magnitude": "properties.mag" }
}
```

Nenhuma linha da plataforma foi alterada para suportar essas fontes: só os dois arquivos de schema e o coletor.

## Configuração

| Variável | Padrão | |
|---|---|---|
| `DEMO_JOBS` | `usgs,openmeteo` | Jobs ativos. |
| `DEMO_INTERVAL_SECONDS` | `300` | Intervalo entre ciclos (mínimo 60). |
| `DEMO_CHUNK_SIZE` | `500` | Itens por lote enviado. |
| `USGS_FEED_URL` | feed `all_day` | Troque por `all_hour` ou `all_week` se quiser. |
| `DEMO_METRICS_PORT` | `9103` | Métricas Prometheus (`argos_demo_*`). |

Os usos de API são gratuitos e sem chave, mas têm limites de cortesia: o intervalo padrão de 5 minutos fica bem abaixo deles.
