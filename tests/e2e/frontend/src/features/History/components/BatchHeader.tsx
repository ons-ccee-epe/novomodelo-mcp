import { conjuntoLabel, conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { formatDate } from "../format";

interface Props {
  batch: BatchResult;
  isBaseline: boolean;
  canToggle: boolean;
  onToggleBaseline: () => void;
  onDownloadSummary?: () => void;
}

const SINGLE_PREFIX = "pergunta:";

/** Avulsa: o id da pergunta (o texto já está na lista abaixo); demais: o rótulo do conjunto. */
export function headerName(batch: BatchResult): string {
  const c = conjuntoOf(batch);
  return c.startsWith(SINGLE_PREFIX) ? c.slice(SINGLE_PREFIX.length) : conjuntoLabel(c);
}

export function BatchHeader({
  batch,
  isBaseline,
  canToggle,
  onToggleBaseline,
  onDownloadSummary,
}: Props) {
  return (
    <header className="cobre-batch-header">
      <div className="cobre-batch-header-id">
        <h2 className="cobre-batch-title">
          {headerName(batch)} — {formatDate(batch.timestamp)}
        </h2>
        <code className="cobre-muted">{batch.batch_id}</code>
      </div>
      <div className="cobre-batch-header-actions">
        <button
          type="button"
          className="cobre-btn"
          aria-pressed={isBaseline}
          disabled={!canToggle}
          title={
            canToggle ? undefined : "Suba o launcher para alterar a baseline"
          }
          onClick={onToggleBaseline}
        >
          {isBaseline ? "Remover baseline" : "★ Definir como baseline"}
        </button>
        <button
          type="button"
          className="cobre-btn"
          disabled={!onDownloadSummary}
          title={onDownloadSummary ? undefined : "Disponível com os gráficos"}
          onClick={onDownloadSummary}
        >
          ⤓ Baixar resumo
        </button>
      </div>
    </header>
  );
}
