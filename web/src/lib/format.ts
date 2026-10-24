import type { Filters } from "../types";

export const emptyFilters = (): Filters => ({
  event_type: "",
  source: "",
  status: "",
  q: "",
  dims: {},
});

type Primitive = string | number | boolean | undefined | null;

/** Monta a query string ignorando valores vazios. */
export function toQuery(params: Record<string, Primitive>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Converte os filtros da tela nos parâmetros da API (`dim.<chave>` para dimensões). */
export function filterParams(filters: Filters): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.event_type) params.event_type = filters.event_type;
  if (filters.source) params.source = filters.source;
  if (filters.status) params.status = filters.status;
  if (filters.q.trim()) params.q = filters.q.trim();
  for (const [key, value] of Object.entries(filters.dims)) {
    if (key && value) params[`dim.${key}`] = value;
  }
  return params;
}

export function formatDate(value: string | undefined | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

export function formatAge(value: string | undefined | null, now = Date.now()): string {
  if (!value) return "—";
  const seconds = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000));
  if (Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86400)} d`;
}

/** Valor de <input type="datetime-local"> (hora local) para ISO UTC. */
export function localInputToIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export function isoToLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match ? match[1] : fallback;
}

export function hasActiveFilters(filters: Filters): boolean {
  return Object.keys(filterParams(filters)).length > 0;
}
