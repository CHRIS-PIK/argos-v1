import { useCallback, useEffect, useState } from "react";
import { api, saveBlob } from "../api";
import { forgetJob, trackedJobs, type TrackedJob } from "../lib/jobs";
import { formatDate } from "../lib/format";
import type { ExportJob } from "../types";

interface Row {
  tracked: TrackedJob;
  job: ExportJob | null;
  error: string | null;
}

const FINAL = new Set(["done", "failed"]);

export function ExportsPage() {
  const [rows, setRows] = useState<Row[]>(() =>
    trackedJobs().map((tracked) => ({ tracked, job: null, error: null })),
  );
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const tracked = trackedJobs();
    const next = await Promise.all(
      tracked.map(async (t): Promise<Row> => {
        try {
          return { tracked: t, job: await api.exportJob(t.id), error: null };
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          return { tracked: t, job: null, error: message };
        }
      }),
    );
    setRows(next);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pending = rows.some((r) => r.job && !FINAL.has(r.job.status));
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [pending, refresh]);

  const download = async (job: ExportJob) => {
    setDownloadError(null);
    try {
      const { blob, filename } = await api.downloadExport(job);
      saveBlob(blob, filename);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = (id: string) => {
    forgetJob(id);
    setRows((current) => current.filter((r) => r.tracked.id !== id));
  };

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Exportações</h1>
          <p className="muted">
            Arquivos gerados em segundo plano ficam disponíveis por 24 horas.
          </p>
        </div>
      </header>

      {downloadError && <p className="error" role="alert">{downloadError}</p>}
      {rows.length === 0 && <p className="empty">Nenhuma exportação ainda. Use “Exportar” nas telas de entidades ou eventos.</p>}

      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Exportação</th>
                <th>Criada em</th>
                <th>Estado</th>
                <th>Linhas</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ tracked, job, error }) => (
                <tr key={tracked.id}>
                  <td>{tracked.label}</td>
                  <td className="nowrap">{formatDate(tracked.createdAt)}</td>
                  <td>
                    {error ? (
                      <span className="muted" title={error}>expirada</span>
                    ) : job ? (
                      <span className={`badge ${job.status === "done" ? "good" : job.status === "failed" ? "bad" : "neutral"}`}>
                        {{ queued: "na fila", running: "gerando", done: "pronta", failed: "falhou" }[job.status]}
                      </span>
                    ) : (
                      "…"
                    )}
                    {job?.error && <div className="error small">{job.error}</div>}
                  </td>
                  <td>
                    {job?.rows !== undefined ? job.rows.toLocaleString("pt-BR") : "—"}
                    {job?.truncated && (
                      <div className="notice small">Cortado em {job.rows?.toLocaleString("pt-BR")} de {job.total?.toLocaleString("pt-BR")}</div>
                    )}
                  </td>
                  <td className="actions-cell">
                    {job?.status === "done" && (
                      <button type="button" className="primary" onClick={() => void download(job)}>
                        Baixar
                      </button>
                    )}
                    <button type="button" className="link" onClick={() => remove(tracked.id)}>
                      Remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
