import type { ReactNode } from "react";

import type { TestResult } from "@/shared/types";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="cobre-field-label">{label}</div>
      {children}
    </div>
  );
}

function ToolCalls({ calls }: { calls: TestResult["all_tool_calls"] }) {
  if (calls.length === 0) {
    return <em className="cobre-muted">Nenhuma tool call registrada</em>;
  }
  return (
    <ol className="cobre-tool-call-list">
      {calls.map((tc, i) => (
        <li key={tc.tool_id ?? i}>
          <code>{tc.name}</code>
          <pre className="cobre-pre-wrap">{JSON.stringify(tc.args ?? {}, null, 2)}</pre>
        </li>
      ))}
    </ol>
  );
}

const ms = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v)} ms` : "—");

/** Detalhe expandido de uma pergunta. */
export function TestDetail({ tr, expected }: { tr: TestResult; expected: string }) {
  const checks = tr.validation_checks ?? [];
  return (
    <div className="cobre-test-detail">
      <Field label="Pergunta">
        <pre className="cobre-pre-wrap">{tr.query}</pre>
      </Field>
      <Field label="Tool esperada → chamada">
        <code>{expected}</code> → <code>{tr.actual_tool ?? "-"}</code>
      </Field>
      <Field label={`Tool calls (${tr.all_tool_calls.length})`}>
        <ToolCalls calls={tr.all_tool_calls} />
      </Field>
      {checks.length > 0 && (
        <Field label={`Checagens (${checks.length})`}>
          <pre className="cobre-pre-wrap">{JSON.stringify(checks, null, 2)}</pre>
        </Field>
      )}
      <Field label="Latências">
        agente {ms(tr.latency_ms)} · tool {ms(tr.tool_latency_ms)}
      </Field>
      {tr.error_message && (
        <Field label="Erro">
          <pre className="cobre-pre-wrap" data-kind="error">
            {tr.error_message}
          </pre>
        </Field>
      )}
      {tr.agent_response && (
        <details>
          <summary className="cobre-summary-toggle">Resposta do agente</summary>
          <pre className="cobre-pre-wrap cobre-pre-scroll">{tr.agent_response}</pre>
        </details>
      )}
    </div>
  );
}
