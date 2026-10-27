import type { ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { TestResult } from "@/shared/types";

/** Chave que o agente põe nos args para explicar a chamada; vira texto, não JSON. */
const PURPOSE_KEY = "__tool_use_purpose";

function MetaItem({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="cobre-detail-section">
      <div className="cobre-muted cobre-detail-label">{label}</div>
      {children}
    </div>
  );
}

function ToolCalls({ calls }: { calls: TestResult["all_tool_calls"] }) {
  if (calls.length === 0) {
    return <p className="cobre-muted cobre-detail-hint">Nenhuma tool chamada.</p>;
  }
  return (
    <ol className="cobre-call-list">
      {calls.map((tc, i) => {
        const { [PURPOSE_KEY]: purpose, ...args } = tc.args ?? {};
        const head = (
          <>
            <code className="cobre-call-name">{tc.name}</code>
            {typeof purpose === "string" && <span className="cobre-call-purpose">{purpose}</span>}
          </>
        );
        return (
          <li key={tc.tool_id ?? i} className="cobre-call">
            {Object.keys(args).length > 0 ? (
              <details>
                <summary className="cobre-call-head">{head}</summary>
                <pre className="cobre-code">{JSON.stringify(args, null, 2)}</pre>
              </details>
            ) : (
              <div className="cobre-call-head">{head}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Checks({ checks }: { checks: TestResult["validation_checks"] }) {
  return (
    <ul className="cobre-check-list">
      {checks.map((c, i) => {
        const passed = c.passed === true;
        const text = typeof c.message === "string" ? c.message : String(c.name ?? "");
        return (
          <li key={`${String(c.name)}-${i}`}>
            <span className="cobre-status" data-status={passed ? "pass" : "fail"}>
              {passed ? "✓ ok" : "✗ falhou"}
            </span>
            <span>{text}</span>
          </li>
        );
      })}
    </ul>
  );
}

const ms = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v)} ms` : "—");

/** Detalhe de uma pergunta já executada, nas abas Testes Funcionais e Histórico. */
export function TestDetail({
  tr,
  expected,
  timeout,
}: {
  tr: TestResult;
  expected: string;
  /** Timeout do caso, quando a tela o conhece (o registro da bateria não guarda). */
  timeout?: string;
}) {
  // Um launcher antigo publica só um resumo do caso (sem estas listas e com
  // response_preview); ler .length direto derruba a tela inteira.
  const checks = tr.validation_checks ?? [];
  const tags = tr.tags ?? [];
  const calls = tr.all_tool_calls as TestResult["all_tool_calls"] | undefined;
  const response =
    tr.agent_response ?? (tr as { response_preview?: string }).response_preview ?? "";
  return (
    <div className="cobre-test-detail">
      <dl className="cobre-detail-meta">
        <MetaItem term="Tool esperada">
          <code>{expected}</code>
        </MetaItem>
        {timeout && <MetaItem term="Timeout">{timeout}</MetaItem>}
        <MetaItem term="Tool chamada">
          <code>{tr.actual_tool ?? "—"}</code>
        </MetaItem>
        <MetaItem term="MCP usado">{tr.mcp_used ? "sim" : "não"}</MetaItem>
        <MetaItem term="Tempo do agente">{ms(tr.latency_ms)}</MetaItem>
        <MetaItem term="Tempo na tool">{ms(tr.tool_latency_ms)}</MetaItem>
        {tags.length > 0 && (
          <MetaItem term="Tags">
            {tags.map((t) => (
              <span key={t} className="cobre-tag-chip">
                {t}
              </span>
            ))}
          </MetaItem>
        )}
      </dl>
      {checks.length > 0 && (
        <Section label={`Checagens (${checks.length})`}>
          <Checks checks={checks} />
        </Section>
      )}
      {calls && (
        <Section label={`Tools chamadas (${calls.length})`}>
          <ToolCalls calls={calls} />
        </Section>
      )}
      {tr.error_message && (
        <Section label="Erro">
          <pre className="cobre-code cobre-detail-error">{tr.error_message}</pre>
        </Section>
      )}
      {response && (
        <Section label="Resposta do agente">
          <div className="cobre-markdown cobre-detail-response">
            <Markdown remarkPlugins={[remarkGfm]}>{response}</Markdown>
          </div>
        </Section>
      )}
    </div>
  );
}
