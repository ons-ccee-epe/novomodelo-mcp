import type { ReactNode } from "react";

import type { RunResultItem } from "@/services/launcherApi";
import { statusIcon } from "@/shared/constants/status";

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

function MetaItem({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function CaseMetaList({ caseMeta, result }: Pick<Props, "caseMeta" | "result">) {
  return (
    <dl className="cobre-detail-meta">
      <MetaItem term="Tool esperada">
        <code>{caseMeta.expected}</code>
      </MetaItem>
      {caseMeta.timeoutS !== null && (
        <MetaItem term="Timeout">{formatDuration(caseMeta.timeoutS)}</MetaItem>
      )}
      {result && (
        <>
          <MetaItem term="Tool chamada">
            <code>{result.actual_tool ?? "—"}</code>
          </MetaItem>
          <MetaItem term="MCP usado">{result.mcp_used ? "sim" : "não"}</MetaItem>
          <MetaItem term="Tempo">{result.latency_ms.toFixed(0)}ms</MetaItem>
        </>
      )}
      {caseMeta.tags.length > 0 && (
        <MetaItem term="Tags">
          {caseMeta.tags.map((t) => (
            <span key={t} className="cobre-tag-chip">
              {t}
            </span>
          ))}
        </MetaItem>
      )}
    </dl>
  );
}

function DetailSection({ label, text, kind }: { label: string; text: string; kind?: string }) {
  return (
    <div className="cobre-detail-section">
      <div className="cobre-muted cobre-detail-label">{label}</div>
      <pre className={`cobre-code${kind ? ` cobre-detail-${kind}` : ""}`}>{text}</pre>
    </div>
  );
}

/** Painel de detalhe de um caso: cabeçalho, prompt e resultado ao vivo. */
export function CaseDetail({ caseMeta, result, running, canRun, onRun }: Props) {
  return (
    <>
      <div className="cobre-detail-head">
        <div>
          <code className="cobre-detail-id">{caseMeta.id}</code>
          {result && (
            <span className="cobre-status cobre-detail-status" data-status={result.status}>
              {statusIcon(result.status)} {result.status}
            </span>
          )}
          {running && <span className="cobre-detail-status cobre-muted">rodando…</span>}
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

      <CaseMetaList caseMeta={caseMeta} result={result} />
      <DetailSection label="Prompt" text={caseMeta.query} />
      {result?.error_message && (
        <DetailSection label="Erro" text={result.error_message} kind="error" />
      )}
      {result?.response_preview && (
        <DetailSection
          label="Resposta do agente (trecho)"
          text={result.response_preview}
          kind="response"
        />
      )}
      {!result && !running && (
        <div className="cobre-muted cobre-detail-hint">
          Este teste ainda não rodou nesta sessão. Clique em “rodar este teste” ou dispare a
          esteira/grupo.
        </div>
      )}
    </>
  );
}
