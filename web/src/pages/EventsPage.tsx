import { useMemo, useState } from "react";
import { api } from "../api";
import { EntityTable } from "../components/EntityTable";
import { ExportDialog } from "../components/ExportDialog";
import { FilterBar } from "../components/FilterBar";
import { usePaged } from "../hooks";
import { emptyFilters, isoToLocalInput, localInputToIso } from "../lib/format";
import type { Entity, Filters, TimeRange } from "../types";
import { openEntity } from "./EntitiesPage";

const PRESETS: { label: string; hours: number }[] = [
  { label: "1 h", hours: 1 },
  { label: "24 h", hours: 24 },
  { label: "7 dias", hours: 24 * 7 },
  { label: "30 dias", hours: 24 * 30 },
];

export function EventsPage() {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [fromInput, setFromInput] = useState(() =>
    isoToLocalInput(new Date(Date.now() - 24 * 3600 * 1000)),
  );
  const [toInput, setToInput] = useState(() => isoToLocalInput(new Date()));
  const [exporting, setExporting] = useState(false);

  const range: TimeRange | null = useMemo(() => {
    const from = localInputToIso(fromInput);
    const to = localInputToIso(toInput);
    return from && to && from < to ? { from, to } : null;
  }, [fromInput, toInput]);

  const key = JSON.stringify([filters, range]);
  const list = usePaged<Entity>(
    (cursor, signal) =>
      range
        ? api.events(filters, range, cursor, signal)
        : Promise.resolve({ items: [], next_cursor: null }),
    [key],
  );

  const applyPreset = (hours: number) => {
    const now = new Date();
    setToInput(isoToLocalInput(now));
    setFromInput(isoToLocalInput(new Date(now.getTime() - hours * 3600 * 1000)));
  };

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Eventos</h1>
          <p className="muted">Histórico em janelas de 10 minutos, do mais recente para o mais antigo.</p>
        </div>
        <button type="button" onClick={() => setExporting(true)} disabled={!range}>
          Exportar
        </button>
      </header>

      <div className="filters">
        <label>
          De
          <input type="datetime-local" value={fromInput} onChange={(e) => setFromInput(e.target.value)} />
        </label>
        <label>
          Até
          <input type="datetime-local" value={toInput} onChange={(e) => setToInput(e.target.value)} />
        </label>
        <div className="presets">
          {PRESETS.map((p) => (
            <button type="button" key={p.label} onClick={() => applyPreset(p.hours)}>
              Últimos {p.label}
            </button>
          ))}
        </div>
      </div>
      {!range && <p className="error">O período é inválido: "De" precisa ser anterior a "Até".</p>}

      <FilterBar filters={filters} onChange={setFilters} />

      {list.error && <p className="error" role="alert">{list.error}</p>}
      <EntityTable rows={list.items} showBucket onOpen={openEntity} />
      {range && !list.loading && !list.error && list.items.length === 0 && (
        <p className="empty">Nenhum evento nesse período.</p>
      )}
      <div className="more">
        {list.loading && <span className="muted">Carregando…</span>}
        {list.hasMore && !list.loading && (
          <button type="button" onClick={list.loadMore}>
            Carregar mais
          </button>
        )}
      </div>

      {exporting && range && (
        <ExportDialog dataset="events" filters={filters} range={range} onClose={() => setExporting(false)} />
      )}
    </section>
  );
}
