import { formatDate } from "../lib/format";
import type { Entity } from "../types";

interface Props {
  rows: Entity[];
  showBucket?: boolean;
  onOpen: (row: Entity) => void;
}

export function StatusBadge({ status }: { status: string }) {
  if (!status) return <span className="muted">—</span>;
  const tone = /^(up|ok|online|healthy|active|connected|closed|resolved)$/i.test(status)
    ? "good"
    : /^(down|error|failed|offline|critical|major|open|unhealthy)$/i.test(status)
      ? "bad"
      : "neutral";
  return <span className={`badge ${tone}`}>{status}</span>;
}

export function EntityTable({ rows, showBucket = false, onOpen }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Tipo</th>
            <th>Fonte</th>
            <th>Id</th>
            <th>Nome</th>
            <th>Status</th>
            <th>Dimensões</th>
            <th>{showBucket ? "Janela (10 min)" : "Coletado em"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.event_type}|${row.source}|${row.entity_id}|${row.bucket_at ?? ""}`}
              tabIndex={0}
              onClick={() => onOpen(row)}
              onKeyDown={(e) => e.key === "Enter" && onOpen(row)}
            >
              <td>{row.event_type}</td>
              <td>{row.source}</td>
              <td className="mono">{row.entity_id}</td>
              <td>{row.name || <span className="muted">—</span>}</td>
              <td>
                <StatusBadge status={row.status} />
              </td>
              <td>
                {Object.entries(row.dimensions).map(([k, v]) => (
                  <span className="chip small" key={k}>
                    {k}: {v}
                  </span>
                ))}
              </td>
              <td className="nowrap">{formatDate(showBucket ? row.bucket_at : row.collected_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
