import { conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { formatDate } from "../format";
import { ConjuntoTag } from "./ConjuntoTag";

const SHORT_SHA_CHARS = 7;

interface Props {
  batch: BatchResult;
  isBaseline: boolean;
  canToggle: boolean;
  onToggleBaseline: () => void;
  onDownloadSummary?: () => void;
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
        <h2 className="cobre-batch-title">{formatDate(batch.timestamp)}</h2>
        <ConjuntoTag conjunto={conjuntoOf(batch)} />
        <code className="cobre-muted">{batch.batch_id}</code>
        {batch.cobre_mcp_version && batch.cobre_mcp_version !== "unknown" && (
          <span className="cobre-muted">v{batch.cobre_mcp_version}</span>
        )}
        {batch.git_commit_sha && (
          <code className="cobre-muted" title={batch.git_commit_sha}>
            {batch.git_commit_sha.slice(0, SHORT_SHA_CHARS)}
          </code>
        )}
      </div>
      <div className="cobre-batch-header-actions">
        <button
          type="button"
          className="cobre-btn"
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
