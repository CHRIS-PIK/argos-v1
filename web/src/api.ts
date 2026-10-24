import { filenameFromDisposition, filterParams, toQuery } from "./lib/format";
import type {
  Entity,
  EntityDetail,
  ExportJob,
  ExportOptions,
  Filters,
  Meta,
  Page,
  QueueStatus,
  TimeRange,
} from "./types";

const KEY_STORE = "argos.apiKey";
const BASE = "/api";

export const apiKey = {
  get: (): string | null => sessionStorage.getItem(KEY_STORE),
  set: (value: string) => sessionStorage.setItem(KEY_STORE, value),
  clear: () => sessionStorage.removeItem(KEY_STORE),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === "string" ? d : (d?.msg ?? JSON.stringify(d)))).join("; ");
    }
  } catch {
    // corpo que não é JSON
  }
  return `${response.status} ${response.statusText}`;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const key = apiKey.get();
  if (key) headers.set("X-API-Key", key);
  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (response.status === 401) onUnauthorized();
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await send(path, { signal })).json() as Promise<T>;
}

const PAGE_SIZE = 100;

export const api = {
  meta: (signal?: AbortSignal) => getJson<Meta>("/v1/meta", signal),

  entities: (filters: Filters, cursor: string | null, signal?: AbortSignal) =>
    getJson<Page<Entity>>(
      `/v1/entities${toQuery({ ...filterParams(filters), limit: PAGE_SIZE, cursor })}`,
      signal,
    ),

  entityCount: (filters: Filters, signal?: AbortSignal) =>
    getJson<{ total: number }>(`/v1/entities/count${toQuery(filterParams(filters))}`, signal),

  events: (filters: Filters, range: TimeRange, cursor: string | null, signal?: AbortSignal) =>
    getJson<Page<Entity>>(
      `/v1/events${toQuery({
        ...filterParams(filters),
        from: range.from,
        to: range.to,
        limit: PAGE_SIZE,
        cursor,
      })}`,
      signal,
    ),

  entity: (eventType: string, source: string, entityId: string, signal?: AbortSignal) =>
    getJson<EntityDetail>(
      `/v1/entity${toQuery({ event_type: eventType, source, entity_id: entityId, history: 50 })}`,
      signal,
    ),

  dimensionValues: (eventType: string, key: string, q: string, signal?: AbortSignal) =>
    getJson<{ values: { value: string; entities: number }[] }>(
      `/v1/dimensions/values${toQuery({ event_type: eventType, key, q })}`,
      signal,
    ),

  queue: (signal?: AbortSignal) => getJson<QueueStatus>("/v1/queue", signal),

  /** Download direto (csv/jsonl). Lança ApiError 413 quando o resultado é grande demais. */
  async exportDirect(options: ExportOptions): Promise<{ blob: Blob; filename: string }> {
    const query = toQuery({
      dataset: options.dataset,
      format: options.format,
      ...filterParams(options.filters),
      from: options.dataset === "events" ? options.range?.from : undefined,
      to: options.dataset === "events" ? options.range?.to : undefined,
      include_payload: options.includePayload,
      dimension_columns: options.dimensionColumns.join(","),
    });
    const response = await send(`/v1/export${query}`);
    return {
      blob: await response.blob(),
      filename: filenameFromDisposition(
        response.headers.get("Content-Disposition"),
        `argos-${options.dataset}.${options.format}`,
      ),
    };
  },

  async createExport(options: ExportOptions): Promise<ExportJob> {
    const body = {
      dataset: options.dataset,
      format: options.format,
      event_type: options.filters.event_type || null,
      source: options.filters.source || null,
      status: options.filters.status || null,
      q: options.filters.q.trim() || null,
      dimensions: Object.fromEntries(
        Object.entries(options.filters.dims).filter(([k, v]) => k && v),
      ),
      from: options.dataset === "events" ? (options.range?.from ?? null) : null,
      to: options.dataset === "events" ? (options.range?.to ?? null) : null,
      include_payload: options.includePayload,
      dimension_columns: options.dimensionColumns,
    };
    const response = await send("/v1/exports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return response.json() as Promise<ExportJob>;
  },

  exportJob: (id: string, signal?: AbortSignal) => getJson<ExportJob>(`/v1/exports/${id}`, signal),

  async downloadExport(job: ExportJob): Promise<{ blob: Blob; filename: string }> {
    const response = await send(`/v1/exports/${job.id}/download`);
    return {
      blob: await response.blob(),
      filename: filenameFromDisposition(
        response.headers.get("Content-Disposition"),
        `argos-${job.dataset}.${job.format}`,
      ),
    };
  },
};

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
