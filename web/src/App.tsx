import { useCallback, useEffect, useState } from "react";
import { ApiError, api, apiKey, setUnauthorizedHandler } from "./api";
import { MetaContext } from "./hooks";
import { EntitiesPage } from "./pages/EntitiesPage";
import { EntityPage } from "./pages/EntityPage";
import { EventsPage } from "./pages/EventsPage";
import { ExportsPage } from "./pages/ExportsPage";
import { SourcesPage } from "./pages/SourcesPage";
import type { Meta } from "./types";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || "#/entities");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/entities");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

function Login({ onSuccess, notice }: { onSuccess: (meta: Meta) => void; notice?: string }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(notice ?? null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    apiKey.set(value.trim());
    try {
      onSuccess(await api.meta());
    } catch (err) {
      apiKey.clear();
      setError(
        err instanceof ApiError && err.status === 401
          ? "Chave inválida."
          : err instanceof ApiError && err.status === 403
            ? "Essa chave não pode consultar dados (precisa do papel reader)."
            : err instanceof Error
              ? err.message
              : String(err),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <form onSubmit={submit}>
        <h1>Argos</h1>
        <p className="muted">Informe uma API key de leitura para consultar os dados.</p>
        <label>
          API key
          <input
            type="password"
            autoComplete="off"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="argos_…"
          />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy || !value.trim()}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}

const NAV: { hash: string; label: string }[] = [
  { hash: "#/entities", label: "Entidades" },
  { hash: "#/events", label: "Eventos" },
  { hash: "#/exports", label: "Exportações" },
  { hash: "#/sources", label: "Fontes e fila" },
];

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [booting, setBooting] = useState(() => apiKey.get() !== null);
  const [notice, setNotice] = useState<string | undefined>();
  const hash = useHash();

  const logout = useCallback((message?: string) => {
    apiKey.clear();
    setMeta(null);
    setNotice(message);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => logout("Sessão expirada ou chave revogada."));
  }, [logout]);

  useEffect(() => {
    if (!apiKey.get()) return;
    api
      .meta()
      .then(setMeta)
      .catch(() => apiKey.clear())
      .finally(() => setBooting(false));
  }, []);

  if (booting) return <p className="boot muted">Carregando…</p>;
  if (!meta) return <Login onSuccess={setMeta} notice={notice} />;

  const [path, queryString = ""] = hash.replace(/^#/, "").split("?");
  const query = new URLSearchParams(queryString);

  let page: React.ReactNode;
  switch (path) {
    case "/events":
      page = <EventsPage />;
      break;
    case "/exports":
      page = <ExportsPage />;
      break;
    case "/sources":
      page = <SourcesPage />;
      break;
    case "/entity":
      page = (
        <EntityPage
          eventType={query.get("event_type") ?? ""}
          source={query.get("source") ?? ""}
          entityId={query.get("id") ?? ""}
        />
      );
      break;
    default:
      page = <EntitiesPage />;
  }

  return (
    <MetaContext.Provider value={meta}>
      <header className="topbar">
        <strong className="brand">Argos</strong>
        <nav>
          {NAV.map((item) => (
            <a
              key={item.hash}
              href={item.hash}
              aria-current={hash.startsWith(item.hash) ? "page" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <span className="spacer" />
        <span className="muted tenant">{meta.tenant_id}</span>
        <button type="button" className="link" onClick={() => logout()}>
          Sair
        </button>
      </header>
      <main className="content">{page}</main>
    </MetaContext.Provider>
  );
}
