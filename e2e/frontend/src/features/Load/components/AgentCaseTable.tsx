import type { AgentStats } from "@/shared/types";
import { fmtMean, fmtMs, fmtPercent } from "../format";

interface Props {
  perCase: Record<string, AgentStats & { group: string }>;
}

/** Execuções por status, aprovação e latência de cada caso da carga. */
export function AgentCaseTable({ perCase }: Props) {
  const rows = Object.entries(perCase).sort(
    ([idA, a], [idB, b]) => a.group.localeCompare(b.group) || idA.localeCompare(idB),
  );
  if (rows.length === 0) return <div className="nm-no-data">Nenhuma execução registrada</div>;

  return (
    <table className="nm-table nm-load-table" aria-label="Métricas por caso">
      <thead>
        <tr>
          <th>Caso</th>
          <th>Grupo</th>
          <th>Execuções</th>
          <th>Aprovados</th>
          <th>Parciais</th>
          <th>Reprovados</th>
          <th>Timeouts</th>
          <th>Erros</th>
          <th>Aprovação</th>
          <th>p50</th>
          <th>p95</th>
          <th>p99</th>
          <th>Tool-calls méd.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([id, s]) => (
          <tr key={id}>
            <td>
              <code>{id}</code>
            </td>
            <td>{s.group}</td>
            <td>{s.calls}</td>
            <td>{s.statuses.pass ?? 0}</td>
            <td>{s.statuses.partial ?? 0}</td>
            <td>{s.statuses.fail ?? 0}</td>
            <td>{s.statuses.timeout ?? 0}</td>
            <td>{s.statuses.error ?? 0}</td>
            <td>{s.calls > 0 ? fmtPercent(s.pass_rate) : "—"}</td>
            <td>{fmtMs(s.p50_ms)}</td>
            <td>{fmtMs(s.p95_ms)}</td>
            <td>{fmtMs(s.p99_ms)}</td>
            <td>{fmtMean(s.tool_calls_mean)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
