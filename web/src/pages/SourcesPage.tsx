import { api } from "../api";
import { useLoad, useMeta } from "../hooks";
import { formatAge } from "../lib/format";

const STALE_MINUTES = 30;

export function SourcesPage() {
  const meta = useMeta();
  const queue = useLoad((signal) => api.queue(signal), []);
  const forbidden = queue.error !== null && /admin role/i.test(queue.error);

  const rows = meta.types.flatMap((t) =>
    t.sources.map((s) => ({ eventType: t.event_type, ...s })),
  );

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Fontes e fila</h1>
          <p className="muted">Quando cada fonte enviou dados pela última vez.</p>
        </div>
      </header>

      {rows.length === 0 && <p className="empty">Nenhuma fonte enviou dados ainda.</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fonte</th>
                <th>Tipo</th>
                <th>Entidades</th>
                <th>Último envio</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const minutes = (Date.now() - new Date(r.last_ingested).getTime()) / 60000;
                return (
                  <tr key={`${r.source}|${r.eventType}`}>
                    <td>{r.source}</td>
                    <td>{r.eventType}</td>
                    <td>{r.entities.toLocaleString("pt-BR")}</td>
                    <td>há {formatAge(r.last_ingested)}</td>
                    <td>
                      {minutes > STALE_MINUTES ? (
                        <span className="badge bad">sem dados recentes</span>
                      ) : (
                        <span className="badge good">em dia</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <h2>Fila</h2>
      {queue.loading && <p className="muted">Carregando…</p>}
      {forbidden && <p className="muted">A fila só aparece para chaves com papel admin.</p>}
      {queue.error && !forbidden && <p className="error">{queue.error}</p>}
      {queue.data && (
        <>
          <dl className="facts">
            <div>
              <dt>Aguardando</dt>
              <dd>{queue.data.waiting}</dd>
            </div>
            <div>
              <dt>Em processamento</dt>
              <dd>{queue.data.processing}</dd>
            </div>
            <div>
              <dt>Mortas (dead-letter)</dt>
              <dd>{queue.data.dead}</dd>
            </div>
            <div>
              <dt>Mais antiga</dt>
              <dd>{formatAge(new Date(Date.now() - queue.data.oldest_age_seconds * 1000).toISOString())}</dd>
            </div>
          </dl>
          {queue.data.recent_dead.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Fonte</th>
                    <th>Tentativas</th>
                    <th>Erro</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.data.recent_dead.map((d) => (
                    <tr key={d.id}>
                      <td>{d.event_type}</td>
                      <td>{d.source}</td>
                      <td>{d.attempts}</td>
                      <td className="mono small">{d.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
