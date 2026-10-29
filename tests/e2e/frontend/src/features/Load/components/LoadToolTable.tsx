import type { LoadStats } from "@/shared/types";
import { fmtMs, fmtPercent, fmtRate } from "../format";

interface Props {
  perTool: Record<string, LoadStats>;
}

/** Contagens, taxa de erro, vazão e latência de cada tool do mix. */
export function LoadToolTable({ perTool }: Props) {
  const rows = Object.entries(perTool).sort(([a], [b]) => a.localeCompare(b));
  if (rows.length === 0) return <div className="nm-no-data">Nenhuma chamada registrada</div>;

  return (
    <table className="nm-table nm-load-table" aria-label="Métricas por tool">
      <thead>
        <tr>
          <th>Tool</th>
          <th>Chamadas</th>
          <th>OK</th>
          <th>Erros</th>
          <th>Timeouts</th>
          <th>Taxa de erro</th>
          <th>Vazão</th>
          <th>p50</th>
          <th>p95</th>
          <th>p99</th>
          <th>Máx</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([tool, s]) => (
          <tr key={tool}>
            <td>
              <code>{tool}</code>
            </td>
            <td>{s.calls}</td>
            <td>{s.ok}</td>
            <td>{s.errors}</td>
            <td>{s.timeouts}</td>
            <td>{fmtPercent(s.error_rate)}</td>
            <td>{fmtRate(s.throughput_cps)}</td>
            <td>{fmtMs(s.p50_ms)}</td>
            <td>{fmtMs(s.p95_ms)}</td>
            <td>{fmtMs(s.p99_ms)}</td>
            <td>{fmtMs(s.max_ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
