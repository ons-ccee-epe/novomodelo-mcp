import type { LoadCapacity } from "@/services/loadApi";
import { fmtMb, fmtMbFine } from "../format";
import { LoadBadges } from "./LoadBadges";

interface Props {
  capacity: LoadCapacity | null;
  error: string | null;
}

/** Até quatro nomes e "+N": a lista completa vem no ``title``. */
function nameList(names: string[]): string {
  const shown = names.slice(0, 4).join(", ");
  return names.length > 4 ? `${shown} +${names.length - 4}` : shown;
}

/** Limite de cada fator, na mesma ordem da conta do backend; o de disco só existe se a seleção grava. */
function factorsLine(limits: LoadCapacity["limits"]): string {
  const parts = [
    `teto do modo ${limits.hard_cap}`,
    `CPU ${limits.cpu}`,
    `memória ${limits.memory ?? "—"}`,
  ];
  if (typeof limits.disk === "number") parts.push(`disco ${limits.disk}`);
  return parts.join(" · ");
}

/** Custo estimado de uma sessão: RAM, núcleos e, se a seleção grava, o disco da cópia + folga. */
function costLine(capacity: LoadCapacity): string {
  const { per_session: p, disk } = capacity;
  const profile = p.profile ? ` (${p.profile})` : "";
  const parts = [`${fmtMb(p.rss_mb)} de RAM`, `${Number(p.cpu_cores.toFixed(2))} núcleo(s)`];
  if (disk) {
    const slack = Math.max(0, disk.per_session_mb - disk.copy_mb);
    parts.push(
      `${fmtMbFine(disk.per_session_mb)} de disco (cópia ${fmtMbFine(disk.copy_mb)} + folga ${fmtMbFine(slack)})`,
    );
  }
  return `Custo por sessão${profile}: ${parts.join(" · ")} · ${p.source}`;
}

/** Quantas sessões simultâneas a máquina aguenta numa linha; a conta, o custo e os avisos ficam recolhidos. */
export function LoadCapacityHint({ capacity, error }: Props) {
  if (!capacity) {
    return (
      <div className="nm-muted nm-load-note">
        {error
          ? `Capacidade da máquina indisponível: ${error}`
          : "Estimando a capacidade da máquina…"}
      </div>
    );
  }
  const selection = capacity.selection;
  return (
    <details className="nm-load-capacity" aria-label="Capacidade da máquina">
      <summary className="nm-load-capacity-summary">
        <span>
          Capacidade da máquina:{" "}
          <strong>{`até ≈ ${capacity.recommended} sessões simultâneas`}</strong>
          <span className="nm-muted">{` (limite: ${capacity.limiting_factor})`}</span>
        </span>
        <span className="nm-mix-edit">Ver cálculo</span>
      </summary>
      <div className="nm-load-capacity-body">
        <div className="nm-muted nm-load-note">{capacity.explanation}</div>
        <div className="nm-muted nm-load-note">{`Limite por fator: ${factorsLine(capacity.limits)}`}</div>
        <div className="nm-muted nm-load-note">{costLine(capacity)}</div>
        {selection && (selection.heavy || selection.writes) && (
          <div className="nm-load-note nm-load-selection" aria-label="Custo da seleção">
            <LoadBadges writes={selection.writes} heavy={selection.heavy} />
            {selection.heavy && (
              <span title={selection.heavy_tools.join(", ")}>
                {`Seleção pesada: sobe o bridge ou o solver (${nameList(selection.heavy_tools)}).`}
              </span>
            )}
            {selection.writes && (
              <span title={selection.write_tools.join(", ")}>
                {`Seleção que grava: cada sessão copia ${fmtMbFine(selection.copy_mb)} de fixtures`}
                {selection.subtrees.length > 0 ? ` (${selection.subtrees.join(", ")})` : ""}.
              </span>
            )}
          </div>
        )}
        {capacity.warnings.map((message) => (
          <div key={message} className="nm-muted nm-load-note">
            ⚠ {message}
          </div>
        ))}
      </div>
    </details>
  );
}
