import { useState } from "react";
import { ApiError, api, saveBlob } from "../api";
import { useMeta } from "../hooks";
import { trackJob } from "../lib/jobs";
import { filterParams } from "../lib/format";
import type { Dataset, ExportFormat, Filters, TimeRange } from "../types";

interface Props {
  dataset: Dataset;
  filters: Filters;
  range?: TimeRange;
  onClose: () => void;
}

const FORMATS: { value: ExportFormat; label: string; hint: string }[] = [
  { value: "csv", label: "CSV", hint: "Abre no Excel; download imediato quando o resultado é pequeno." },
  { value: "jsonl", label: "JSON Lines", hint: "Um objeto por linha, bom para scripts." },
  { value: "xlsx", label: "Excel (.xlsx)", hint: "Gerado em segundo plano. Máximo de ~1 milhão de linhas." },
  { value: "parquet", label: "Parquet", hint: "Gerado em segundo plano. Ideal para análise (Python, Power BI)." },
];

export function ExportDialog({ dataset, filters, range, onClose }: Props) {
  const meta = useMeta();
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [includePayload, setIncludePayload] = useState(false);
  const [dimensionColumns, setDimensionColumns] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const scope = meta.types.filter((t) => !filters.event_type || t.event_type === filters.event_type);
  const keys = [...new Set(scope.flatMap((t) => t.dimensions.map((d) => d.key)))].sort();

  const toggleKey = (key: string) =>
    setDimensionColumns((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    );

  const submit = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const options = { dataset, format, filters, range, includePayload, dimensionColumns };
    try {
      if (format === "csv" || format === "jsonl") {
        try {
          const { blob, filename } = await api.exportDirect(options);
          saveBlob(blob, filename);
          onClose();
          return;
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 413)) throw err;
          setNotice("Resultado grande: gerando em segundo plano.");
        }
      }
      const job = await api.createExport(options);
      const label = [dataset, ...Object.values(filterParams(filters)).slice(0, 2), format].join(" · ");
      trackJob({ id: job.id, label, createdAt: job.created_at });
      window.location.hash = "#/exports";
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Exportar">
      <div className="dialog">
        <h2>Exportar {dataset === "entities" ? "entidades" : "eventos"}</h2>
        <p className="muted">Usa os filtros atuais da tela.</p>

        <fieldset>
          <legend>Formato</legend>
          {FORMATS.map((f) => (
            <label key={f.value} className="radio">
              <input
                type="radio"
                name="format"
                checked={format === f.value}
                onChange={() => setFormat(f.value)}
              />
              <span>
                {f.label}
                <small className="muted"> — {f.hint}</small>
              </span>
            </label>
          ))}
        </fieldset>

        {keys.length > 0 && (
          <fieldset>
            <legend>Dimensões como colunas</legend>
            <div className="checks">
              {keys.map((k) => (
                <label key={k} className="check">
                  <input
                    type="checkbox"
                    checked={dimensionColumns.includes(k)}
                    onChange={() => toggleKey(k)}
                  />
                  {k}
                </label>
              ))}
            </div>
            <small className="muted">
              Sem seleção, as dimensões saem juntas em uma coluna JSON.
            </small>
          </fieldset>
        )}

        <label className="check">
          <input
            type="checkbox"
            checked={includePayload}
            onChange={(e) => setIncludePayload(e.target.checked)}
          />
          Incluir o payload completo (JSON) de cada item
        </label>

        {notice && <p className="notice">{notice}</p>}
        {error && <p className="error" role="alert">{error}</p>}

        <div className="actions">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="button" className="primary" onClick={submit} disabled={busy}>
            {busy ? "Exportando…" : "Exportar"}
          </button>
        </div>
      </div>
    </div>
  );
}
