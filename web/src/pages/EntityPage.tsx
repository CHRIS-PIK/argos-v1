import { Fragment, useState } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/EntityTable";
import { useLoad } from "../hooks";
import { formatDate } from "../lib/format";

interface Props {
  eventType: string;
  source: string;
  entityId: string;
}

export function EntityPage({ eventType, source, entityId }: Props) {
  const { data, error, loading } = useLoad(
    (signal) => api.entity(eventType, source, entityId, signal),
    [eventType, source, entityId],
  );
  const [openRow, setOpenRow] = useState<string | null>(null);

  return (
    <section>
      <p>
        <a href="#/entities">← Entidades</a>
      </p>
      {loading && <p className="muted">Carregando…</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {data && (
        <>
          <header className="page-head">
            <div>
              <h1>{data.entity.name || data.entity.entity_id}</h1>
              <p className="muted mono">
                {data.entity.event_type} · {data.entity.source} · {data.entity.entity_id}
              </p>
            </div>
            <StatusBadge status={data.entity.status} />
          </header>

          <dl className="facts">
            <div>
              <dt>Coletado em</dt>
              <dd>{formatDate(data.entity.collected_at)}</dd>
            </div>
            <div>
              <dt>Recebido em</dt>
              <dd>{formatDate(data.entity.ingested_at)}</dd>
            </div>
            <div>
              <dt>Versão do schema</dt>
              <dd>{data.entity.schema_version}</dd>
            </div>
            {Object.entries(data.entity.dimensions).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>

          <h2>Payload atual</h2>
          <pre className="json">{JSON.stringify(data.entity.payload, null, 2)}</pre>

          <h2>Histórico recente</h2>
          {data.history.length === 0 && <p className="empty">Sem histórico.</p>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Janela (10 min)</th>
                  <th>Status</th>
                  <th>Nome</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((row) => {
                  const key = row.bucket_at ?? row.collected_at;
                  const expanded = openRow === key;
                  return (
                    <Fragment key={key}>
                      <tr>
                        <td className="nowrap">{formatDate(row.bucket_at)}</td>
                        <td>
                          <StatusBadge status={row.status} />
                        </td>
                        <td>{row.name || "—"}</td>
                        <td>
                          <button type="button" className="link" onClick={() => setOpenRow(expanded ? null : key)}>
                            {expanded ? "Ocultar" : "Ver payload"}
                          </button>
                        </td>
                      </tr>
                      {expanded && (
                        <tr>
                          <td colSpan={4}>
                            <pre className="json">{JSON.stringify(row.payload, null, 2)}</pre>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
