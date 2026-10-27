import type { RunResultItem } from "@/services/launcherApi";
import { TestDetail } from "@/shared/components/TestDetail";
import { STATUS_LABEL, statusIcon } from "@/shared/constants/status";

export interface CaseSummary {
  id: string;
  query: string;
  expected: string;
  tags: string[];
  timeoutS: number | null;
}

interface Props {
  caseMeta: CaseSummary;
  result: RunResultItem | null;
  running: boolean;
  canRun: boolean;
  onRun: () => void;
}

function formatDuration(seconds: number): string {
  return seconds >= 60 && seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds}s`;
}

/** O que se sabe do caso antes de ele rodar: tool esperada, timeout e tags. */
function PendingMeta({ caseMeta }: { caseMeta: CaseSummary }) {
  return (
    <dl className="cobre-detail-meta">
      <div>
        <dt>Tool esperada</dt>
        <dd>
          <code>{caseMeta.expected}</code>
        </dd>
      </div>
      {caseMeta.timeoutS !== null && (
        <div>
          <dt>Timeout</dt>
          <dd>{formatDuration(caseMeta.timeoutS)}</dd>
        </div>
      )}
      {caseMeta.tags.length > 0 && (
        <div>
          <dt>Tags</dt>
          <dd>
            {caseMeta.tags.map((t) => (
              <span key={t} className="cobre-tag-chip">
                {t}
              </span>
            ))}
          </dd>
        </div>
      )}
    </dl>
  );
}

/** Painel de detalhe de um caso: cabeçalho, e o resultado completo quando ele já rodou. */
export function CaseDetail({ caseMeta, result, running, canRun, onRun }: Props) {
  return (
    <>
      <div className="cobre-detail-head">
        <div>
          <h2 className="cobre-detail-question">{caseMeta.query}</h2>
          <div className="cobre-detail-sub">
            <code className="cobre-detail-id">{caseMeta.id}</code>
            {result && (
              <span className="cobre-status" data-status={result.status}>
                {statusIcon(result.status)} {STATUS_LABEL[result.status] ?? result.status}
              </span>
            )}
            {running && (
              <span className="cobre-status" data-status="running">
                rodando…
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="cobre-btn cobre-btn-primary"
          onClick={onRun}
          disabled={!canRun}
          title="Dispara só este caso no provedor selecionado"
        >
          ▶ rodar este teste
        </button>
      </div>

      {result ? (
        <TestDetail
          tr={result}
          expected={caseMeta.expected}
          timeout={caseMeta.timeoutS !== null ? formatDuration(caseMeta.timeoutS) : undefined}
        />
      ) : (
        <>
          <PendingMeta caseMeta={caseMeta} />
          {!running && (
            <div className="cobre-muted cobre-detail-hint">
              Este teste ainda não rodou nesta sessão. Clique em “rodar este teste” ou dispare a
              esteira/grupo.
            </div>
          )}
        </>
      )}
    </>
  );
}
