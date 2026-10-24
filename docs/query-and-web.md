# Query API e interface web

```text
navegador ──> web (nginx :8080) ── /api ──> Query API (:8001) ──> ClickHouse
                                                  └─ exportações ──> Redis (estado) + volume /exports (arquivos)
```

O nginx serve a interface e repassa `/api/` para a Query API, então o navegador fala com uma única origem (sem CORS).

## Autenticação

Cada chamada exige `X-API-Key`. Papéis:

| Papel | Pode |
|---|---|
| `collector` | Enviar eventos (`POST /v1/events`). |
| `reader` | Consultar e exportar. |
| `admin` | Tudo, inclusive ver a fila (`GET /v1/queue`). |

```bash
docker compose exec ingest python -m app.ingest.keys create --name ana --tenant default --role reader
docker compose exec ingest python -m app.ingest.keys create --name ops --tenant default --role admin
```

O `tenant_id` e os `event_type` permitidos vêm **sempre da chave**; nenhum parâmetro de requisição os altera. Todos os filtros viram parâmetros ligados do ClickHouse (nada do cliente é concatenado no SQL).

## Endpoints (`app/query`)

| Endpoint | Descrição |
|---|---|
| `GET /v1/meta` | Tipos, fontes (com último envio), status, dimensões e schemas. A interface monta os filtros a partir dele. |
| `GET /v1/entities` | Estado atual. Filtros: `event_type`, `source`, `status`, `q` (nome ou id), `dim.<chave>=<valor>`. Paginação: `limit` (até 1000) e `cursor`. `include_payload=true` traz o item completo. |
| `GET /v1/entities/count` | Total para os mesmos filtros. |
| `GET /v1/entity?event_type&source&entity_id` | Detalhe com payload e histórico recente. |
| `GET /v1/events` | Histórico em janelas de 10 min, do mais novo ao mais antigo. `from` e `to` (ISO 8601; padrão: últimas 24 h). |
| `GET /v1/dimensions/values` | Valores de uma dimensão, para autocompletar filtros. |
| `GET /v1/queue` | Fila e dead-letter (admin). |

A paginação é por **keyset** (o `cursor` é opaco): custo constante em qualquer página, sem `OFFSET`.

## Exportação

- `GET /v1/export?dataset=entities|events&format=csv|jsonl` — download em streaming. Se o resultado passar de `EXPORT_DIRECT_LIMIT` (50 mil linhas), responde `413` pedindo o job.
- `POST /v1/exports` — cria um job (`csv`, `jsonl`, `xlsx` ou `parquet`) e responde `202` com o `id`. Acompanhe em `GET /v1/exports/{id}` e baixe em `GET /v1/exports/{id}/download`.
- Os jobs rodam em threads do próprio serviço `query` (`EXPORT_WORKERS`, padrão 2), gravam em `EXPORT_DIR` e guardam o estado no Redis. Cada job é visível só para o mesmo `tenant_id`.
- Limites: `EXPORT_MAX_ROWS` (1 milhão; acima disso o arquivo é cortado e o job informa `truncated`), 1.048.575 linhas no XLSX. Arquivos e estado expiram em `EXPORT_TTL_SECONDS` (24 h).
- `dimension_columns` transforma dimensões em colunas (`dim.site_name`); sem isso saem juntas em uma coluna JSON. `include_payload` acrescenta o item original.

## Interface (`web/`)

React + Vite + TypeScript, sem bibliotecas além do React.

- **Entidades** e **Eventos**: filtros dinâmicos (tipo, fonte, status, busca, dimensões com autocomplete), tabela com “carregar mais”, exportação.
- **Detalhe**: payload atual e histórico, com payload de cada janela.
- **Exportações**: acompanha os jobs criados neste navegador e baixa os arquivos.
- **Fontes e fila**: último envio por fonte (alerta se passar de 30 min) e estado da fila para admins.
- A chave fica só em `sessionStorage`; “Sair” ou um `401` voltam ao login.

Desenvolvimento:

```bash
cd web
npm ci
npm run dev        # http://localhost:5173, proxy /api -> http://localhost:8001
npm test
npm run build
```

## Limites desta fase

- As exportações rodam no processo `query`: com várias réplicas, o arquivo fica no volume da réplica que o gerou. Em Kubernetes, use um volume compartilhado (RWX) ou armazenamento de objetos.
- A lista de exportações vem do navegador (a API não lista jobs).
- Autenticação por API key. SSO/OIDC pode entrar depois sem mudar a API (basta o gateway traduzir o token em `X-API-Key`/papel).
- O SQL da Query API foi validado por testes de forma e parâmetros, não contra um ClickHouse real.
