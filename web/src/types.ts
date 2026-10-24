export interface Entity {
  tenant_id: string;
  event_type: string;
  source: string;
  schema_version: string;
  entity_id: string;
  name: string;
  status: string;
  dimensions: Record<string, string>;
  collected_at: string;
  ingested_at: string;
  batch_id: string;
  bucket_at?: string;
  payload?: unknown;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface SourceInfo {
  source: string;
  entities: number;
  last_ingested: string;
}

export interface TypeMeta {
  event_type: string;
  entities: number;
  sources: SourceInfo[];
  statuses: string[];
  dimensions: { key: string; distinct_values: number }[];
}

export interface Meta {
  tenant_id: string;
  types: TypeMeta[];
  schemas: { event_type: string; schema_version: string }[];
}

export interface EntityDetail {
  entity: Entity;
  history: Entity[];
}

export interface ExportJob {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  dataset: string;
  format: string;
  created_at: string;
  finished_at?: string;
  rows?: number;
  total?: number;
  truncated?: boolean;
  error?: string;
  download_url?: string;
}

export interface QueueStatus {
  waiting: number;
  processing: number;
  dead: number;
  oldest_age_seconds: number;
  recent_dead: {
    id: string;
    event_type: string | null;
    source: string | null;
    tenant_id: string | null;
    attempts: string | null;
    error: string;
  }[];
}

export interface Filters {
  event_type: string;
  source: string;
  status: string;
  q: string;
  dims: Record<string, string>;
}

export interface TimeRange {
  from: string;
  to: string;
}

export type ExportFormat = "csv" | "jsonl" | "xlsx" | "parquet";
export type Dataset = "entities" | "events";

export interface ExportOptions {
  dataset: Dataset;
  format: ExportFormat;
  filters: Filters;
  range?: TimeRange;
  includePayload: boolean;
  dimensionColumns: string[];
}
