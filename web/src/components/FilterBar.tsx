import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useDebounced, useMeta } from "../hooks";
import type { Filters } from "../types";

interface Props {
  filters: Filters;
  onChange: (next: Filters) => void;
}

export function FilterBar({ filters, onChange }: Props) {
  const meta = useMeta();
  const [search, setSearch] = useState(filters.q);
  const debounced = useDebounced(search, 350);
  const [dimKey, setDimKey] = useState("");
  const [dimValue, setDimValue] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    if (debounced !== filters.q) onChange({ ...filters, q: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const types = meta.types;
  const selectedType = types.find((t) => t.event_type === filters.event_type);

  const sources = useMemo(() => {
    const scope = selectedType ? [selectedType] : types;
    return [...new Set(scope.flatMap((t) => t.sources.map((s) => s.source)))].sort();
  }, [selectedType, types]);

  const statuses = useMemo(() => {
    const scope = selectedType ? [selectedType] : types;
    return [...new Set(scope.flatMap((t) => t.statuses))].sort();
  }, [selectedType, types]);

  const dimensionKeys = useMemo(() => {
    const scope = selectedType ? [selectedType] : types;
    return [...new Set(scope.flatMap((t) => t.dimensions.map((d) => d.key)))].sort();
  }, [selectedType, types]);

  useEffect(() => {
    setSuggestions([]);
    if (!dimKey || !filters.event_type) return;
    const abort = new AbortController();
    api
      .dimensionValues(filters.event_type, dimKey, dimValue, abort.signal)
      .then((r) => setSuggestions(r.values.map((v) => v.value)))
      .catch(() => {});
    return () => abort.abort();
  }, [dimKey, dimValue, filters.event_type]);

  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  const addDimension = () => {
    if (!dimKey || !dimValue) return;
    set({ dims: { ...filters.dims, [dimKey]: dimValue } });
    setDimValue("");
  };

  const removeDimension = (key: string) => {
    const { [key]: _removed, ...rest } = filters.dims;
    set({ dims: rest });
  };

  const clear = () => {
    setSearch("");
    onChange({ event_type: "", source: "", status: "", q: "", dims: {} });
  };

  return (
    <div className="filters">
      <label>
        Tipo
        <select
          value={filters.event_type}
          onChange={(e) => set({ event_type: e.target.value, source: "", status: "", dims: {} })}
        >
          <option value="">Todos</option>
          {types.map((t) => (
            <option key={t.event_type} value={t.event_type}>
              {t.event_type} ({t.entities})
            </option>
          ))}
        </select>
      </label>

      <label>
        Fonte
        <select value={filters.source} onChange={(e) => set({ source: e.target.value })}>
          <option value="">Todas</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label>
        Status
        <select value={filters.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">Todos</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className="grow">
        Buscar (nome ou id)
        <input
          type="search"
          value={search}
          placeholder="ex.: ap-sala-12"
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>

      <div className="dimension-row">
        <label>
          Dimensão
          <select value={dimKey} onChange={(e) => setDimKey(e.target.value)}>
            <option value="">Escolher…</option>
            {dimensionKeys.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          Valor
          <input
            list="dimension-values"
            value={dimValue}
            disabled={!dimKey}
            onChange={(e) => setDimValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addDimension()}
          />
          <datalist id="dimension-values">
            {suggestions.map((v) => (
              <option key={v} value={v} />
            ))}
          </datalist>
        </label>
        <button type="button" onClick={addDimension} disabled={!dimKey || !dimValue}>
          Adicionar
        </button>
      </div>

      {(Object.keys(filters.dims).length > 0 ||
        filters.event_type ||
        filters.source ||
        filters.status ||
        filters.q) && (
        <div className="chips">
          {Object.entries(filters.dims).map(([key, value]) => (
            <span className="chip" key={key}>
              {key}: {value}
              <button type="button" aria-label={`Remover ${key}`} onClick={() => removeDimension(key)}>
                ×
              </button>
            </span>
          ))}
          <button type="button" className="link" onClick={clear}>
            Limpar filtros
          </button>
        </div>
      )}
    </div>
  );
}
