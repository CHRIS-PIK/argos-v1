import { useState } from "react";
import { api } from "../api";
import { EntityTable } from "../components/EntityTable";
import { ExportDialog } from "../components/ExportDialog";
import { FilterBar } from "../components/FilterBar";
import { useLoad, usePaged } from "../hooks";
import { emptyFilters } from "../lib/format";
import type { Entity, Filters } from "../types";

export function openEntity(row: Entity) {
  const params = new URLSearchParams({
    event_type: row.event_type,
    source: row.source,
    id: row.entity_id,
  });
  window.location.hash = `#/entity?${params.toString()}`;
}

export function EntitiesPage() {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [exporting, setExporting] = useState(false);
  const key = JSON.stringify(filters);

  const list = usePaged<Entity>((cursor, signal) => api.entities(filters, cursor, signal), [key]);
  const count = useLoad((signal) => api.entityCount(filters, signal), [key]);

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Entidades</h1>
          <p className="muted">
            Estado atual de cada entidade, de todas as fontes.
            {count.data && <> {count.data.total.toLocaleString("pt-BR")} encontradas.</>}
          </p>
        </div>
        <button type="button" onClick={() => setExporting(true)}>
          Exportar
        </button>
      </header>

      <FilterBar filters={filters} onChange={setFilters} />

      {list.error && <p className="error" role="alert">{list.error}</p>}
      <EntityTable rows={list.items} onOpen={openEntity} />
      {!list.loading && !list.error && list.items.length === 0 && (
        <p className="empty">Nenhuma entidade com esses filtros.</p>
      )}
      <div className="more">
        {list.loading && <span className="muted">Carregando…</span>}
        {list.hasMore && !list.loading && (
          <button type="button" onClick={list.loadMore}>
            Carregar mais
          </button>
        )}
      </div>

      {exporting && (
        <ExportDialog dataset="entities" filters={filters} onClose={() => setExporting(false)} />
      )}
    </section>
  );
}
