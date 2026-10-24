import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Meta, Page } from "./types";

export const MetaContext = createContext<Meta | null>(null);
export const useMeta = (): Meta => {
  const meta = useContext(MetaContext);
  if (!meta) throw new Error("MetaContext ausente");
  return meta;
};

export function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

interface PagedState<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => void;
}

/** Lista paginada por cursor. Recarrega do início sempre que `deps` mudar. */
export function usePaged<T>(
  fetchPage: (cursor: string | null, signal: AbortSignal) => Promise<Page<T>>,
  deps: unknown[],
): PagedState<T> {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;
  const controller = useRef<AbortController | null>(null);

  const run = useCallback((from: string | null, replace: boolean) => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setLoading(true);
    setError(null);
    fetchRef
      .current(from, abort.signal)
      .then((page) => {
        if (abort.signal.aborted) return;
        setItems((current) => (replace ? page.items : [...current, ...page.items]));
        setCursor(page.next_cursor);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (abort.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    setItems([]);
    setCursor(null);
    run(null, true);
    return () => controller.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {
    items,
    loading,
    error,
    hasMore: cursor !== null,
    loadMore: () => {
      if (cursor) run(cursor, false);
    },
  };
}

/** Carrega um valor assíncrono; recarrega quando `deps` mudar. */
export function useLoad<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    loadRef
      .current(abort.signal)
      .then((value) => {
        if (abort.signal.aborted) return;
        setData(value);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (abort.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => abort.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}
