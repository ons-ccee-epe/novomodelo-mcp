import { indexEntryMode, type LoadIndexEntry } from "@/shared/types";
import { fmtCpm, fmtLoadId, fmtMs, fmtPercent, fmtRate } from "../format";

interface Props {
  runs: LoadIndexEntry[];
  selectedId: string | null;
  compareId: string | null;
  /** ``null`` = sem comparação; ``undefined`` = voltar ao padrão (a carga anterior). */
  onCompare: (id: string | null | undefined) => void;
}

function label(r: LoadIndexEntry): string {
  const s = r.summary;
  const partial = r.interrupted ? " (parcial)" : "";
  const sessions = `${r.config.concurrency} sessões ×${r.config.duration_seconds}s`;
  if (indexEntryMode(r) === "agent") {
    const provider = r.config.provider ? ` · ${r.config.provider}` : "";
    return `${fmtLoadId(r.load_id)} | agent${provider} · ${sessions} | ${fmtCpm(
      s.throughput_cpm,
    )} · aprov ${fmtPercent(s.pass_rate)} · p95 ${fmtMs(s.p95_ms)}${partial}`;
  }
  return `${fmtLoadId(r.load_id)} | tools · ${sessions} | ${fmtRate(
    s.throughput_cps,
  )} · err ${fmtPercent(s.error_rate)} · p95 ${fmtMs(s.p95_ms)}${partial}`;
}

/** Escolha da carga de comparação: só as do mesmo modo da carga exibida. */
export function LoadCompareSelect({ runs, selectedId, compareId, onCompare }: Props) {
  const selected = runs.find((r) => r.load_id === selectedId);
  const selectedMode = selected ? indexEntryMode(selected) : null;

  return (
    <div className="cobre-topbar cobre-load-compare">
      <div className="cobre-field">
        <label htmlFor="load-compare-select" className="cobre-field-label">
          Comparar com
        </label>
        <select
          id="load-compare-select"
          className="cobre-select"
          value={compareId ?? ""}
          onChange={(e) => onCompare(e.target.value || null)}
        >
          <option value="">-- Nenhuma --</option>
          {runs
            .filter((r) => r.load_id !== selectedId && indexEntryMode(r) === selectedMode)
            .map((r) => (
              <option key={r.load_id} value={r.load_id}>
                {label(r)}
              </option>
            ))}
        </select>
      </div>

      <button type="button" onClick={() => onCompare(undefined)} className="cobre-reload">
        Comparar com a anterior
      </button>
    </div>
  );
}
