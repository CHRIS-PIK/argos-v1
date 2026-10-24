import { describe, expect, it } from "vitest";
import {
  emptyFilters,
  filenameFromDisposition,
  filterParams,
  formatAge,
  hasActiveFilters,
  isoToLocalInput,
  localInputToIso,
  toQuery,
} from "./format";

describe("toQuery", () => {
  it("ignora valores vazios e codifica os demais", () => {
    expect(toQuery({ a: "x y", b: "", c: undefined, d: 0, e: false })).toBe("?a=x+y&d=0&e=false");
    expect(toQuery({})).toBe("");
  });
});

describe("filterParams", () => {
  it("converte dimensões em dim.<chave> e ignora vazios", () => {
    const filters = {
      ...emptyFilters(),
      event_type: "aps",
      q: "  sala  ",
      dims: { site_name: "HQ", vazio: "" },
    };
    expect(filterParams(filters)).toEqual({ event_type: "aps", q: "sala", "dim.site_name": "HQ" });
  });

  it("detecta filtros ativos", () => {
    expect(hasActiveFilters(emptyFilters())).toBe(false);
    expect(hasActiveFilters({ ...emptyFilters(), status: "Down" })).toBe(true);
  });
});

describe("formatAge", () => {
  const now = new Date("2026-10-24T12:00:00Z").getTime();
  it("escolhe a unidade adequada", () => {
    expect(formatAge("2026-10-24T11:59:30Z", now)).toBe("30s");
    expect(formatAge("2026-10-24T11:50:00Z", now)).toBe("10 min");
    expect(formatAge("2026-10-24T09:00:00Z", now)).toBe("3 h");
    expect(formatAge("2026-10-21T12:00:00Z", now)).toBe("3 d");
    expect(formatAge(undefined, now)).toBe("—");
  });
});

describe("datas locais", () => {
  it("faz o ciclo input local -> ISO -> input local", () => {
    const local = "2026-10-24T09:30";
    const iso = localInputToIso(local);
    expect(iso).toBeDefined();
    expect(isoToLocalInput(new Date(iso as string))).toBe(local);
    expect(localInputToIso("")).toBeUndefined();
  });
});

describe("filenameFromDisposition", () => {
  it("lê o nome do cabeçalho ou usa o padrão", () => {
    expect(filenameFromDisposition('attachment; filename="a.csv"', "x")).toBe("a.csv");
    expect(filenameFromDisposition(null, "x")).toBe("x");
  });
});
