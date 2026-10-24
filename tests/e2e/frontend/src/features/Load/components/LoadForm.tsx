import { useMemo, useState } from "react";

import type { LoadLimits, LoadToolInfo, StartLoadBody } from "@/services/loadApi";

export interface LoadFormValues {
  concurrency: string;
  duration: string;
  iterations: string;
  timeout: string;
  tools: ReadonlySet<string>;
}

export interface ParsedLoadForm {
  body: StartLoadBody | null;
  errors: string[];
}

function parseNumber(raw: string): number | null {
  const text = raw.trim();
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : Number.NaN;
}

/**
 * Valida o formulário contra os limites do launcher e monta o corpo do POST.
 * Com todas as tools disponíveis marcadas, envia ``tools: null`` (mix inteiro).
 */
export function parseLoadForm(
  values: LoadFormValues,
  limits: LoadLimits,
  tools: LoadToolInfo[],
): ParsedLoadForm {
  const errors: string[] = [];

  const concurrency = parseNumber(values.concurrency);
  if (
    concurrency === null ||
    !Number.isInteger(concurrency) ||
    concurrency < limits.min_concurrency ||
    concurrency > limits.max_concurrency
  ) {
    errors.push(
      `Concorrência deve ser um inteiro de ${limits.min_concurrency} a ${limits.max_concurrency}.`,
    );
  }

  const duration = parseNumber(values.duration);
  if (
    duration === null ||
    Number.isNaN(duration) ||
    duration < limits.min_duration_seconds ||
    duration > limits.max_duration_seconds
  ) {
    errors.push(
      `Duração deve ficar entre ${limits.min_duration_seconds} e ${limits.max_duration_seconds} s.`,
    );
  }

  const iterations = parseNumber(values.iterations);
  if (
    iterations !== null &&
    (!Number.isInteger(iterations) || iterations < 1 || iterations > limits.max_iterations)
  ) {
    errors.push(`Iterações por cliente deve ser um inteiro de 1 a ${limits.max_iterations}.`);
  }

  const timeout = parseNumber(values.timeout);
  if (
    timeout !== null &&
    (Number.isNaN(timeout) || timeout <= 0 || timeout > limits.max_timeout_seconds)
  ) {
    errors.push(`Timeout deve ficar entre 0 e ${limits.max_timeout_seconds} s.`);
  }

  const available = tools.filter((t) => t.available).map((t) => t.tool);
  const chosen = available.filter((t) => values.tools.has(t));
  if (chosen.length === 0) errors.push("Escolha ao menos uma tool.");

  if (errors.length > 0) return { body: null, errors };
  return {
    errors,
    body: {
      concurrency: concurrency as number,
      duration_seconds: duration as number,
      iterations: iterations,
      tools: chosen.length === available.length ? null : chosen,
      timeout_seconds: timeout,
    },
  };
}

interface Props {
  tools: LoadToolInfo[];
  limits: LoadLimits;
  disabled: boolean;
  onStart: (body: StartLoadBody) => void;
}

function groupTools(tools: LoadToolInfo[]): Array<[string, LoadToolInfo[]]> {
  const groups = new Map<string, LoadToolInfo[]>();
  for (const tool of tools) groups.set(tool.group, [...(groups.get(tool.group) ?? []), tool]);
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

/** Parâmetros da carga: tools do mix, concorrência, duração (ou iterações) e timeout. */
export function LoadForm({ tools, limits, disabled, onStart }: Props) {
  const [concurrency, setConcurrency] = useState("2");
  const [duration, setDuration] = useState("30");
  const [iterations, setIterations] = useState("");
  const [callTimeout, setCallTimeout] = useState(String(limits.default_timeout_seconds));
  const [selected, setSelected] = useState<ReadonlySet<string>>(
    () => new Set(tools.filter((t) => t.available).map((t) => t.tool)),
  );

  const groups = useMemo(() => groupTools(tools), [tools]);
  const parsed = parseLoadForm(
    { concurrency, duration, iterations, timeout: callTimeout, tools: selected },
    limits,
    tools,
  );

  function toggle(tool: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tool)) next.delete(tool);
      else next.add(tool);
      return next;
    });
  }

  function setAll(on: boolean) {
    setSelected(on ? new Set(tools.filter((t) => t.available).map((t) => t.tool)) : new Set());
  }

  return (
    <form
      className="cobre-load-form"
      aria-label="Parâmetros da carga"
      onSubmit={(e) => {
        e.preventDefault();
        if (parsed.body) onStart(parsed.body);
      }}
    >
      <div className="cobre-form-row">
        <div className="cobre-field">
          <label htmlFor="load-concurrency" className="cobre-field-label">
            Concorrência (clientes)
          </label>
          <input
            id="load-concurrency"
            className="cobre-input"
            type="number"
            inputMode="numeric"
            min={limits.min_concurrency}
            max={limits.max_concurrency}
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="cobre-field">
          <label htmlFor="load-duration" className="cobre-field-label">
            Duração (s)
          </label>
          <input
            id="load-duration"
            className="cobre-input"
            type="number"
            min={limits.min_duration_seconds}
            max={limits.max_duration_seconds}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="cobre-field">
          <label htmlFor="load-iterations" className="cobre-field-label">
            Iterações por cliente (opcional)
          </label>
          <input
            id="load-iterations"
            className="cobre-input"
            type="number"
            min={1}
            max={limits.max_iterations}
            placeholder="sem limite"
            value={iterations}
            onChange={(e) => setIterations(e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="cobre-field">
          <label htmlFor="load-timeout" className="cobre-field-label">
            Timeout por chamada (s)
          </label>
          <input
            id="load-timeout"
            className="cobre-input"
            type="number"
            min={0}
            max={limits.max_timeout_seconds}
            value={callTimeout}
            onChange={(e) => setCallTimeout(e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>

      <fieldset className="cobre-tool-picker" disabled={disabled}>
        <legend className="cobre-field-label">
          Tools do mix (somente leitura){" "}
          <button type="button" className="cobre-btn cobre-btn-ghost" onClick={() => setAll(true)}>
            todas
          </button>{" "}
          <button type="button" className="cobre-btn cobre-btn-ghost" onClick={() => setAll(false)}>
            nenhuma
          </button>
        </legend>
        {groups.map(([group, items]) => (
          <div key={group} className="cobre-tool-group">
            <span className="cobre-muted cobre-tool-group-name">{group}</span>
            {items.map((t) => (
              <label
                key={t.tool}
                className="cobre-tag-option"
                data-active={selected.has(t.tool) && t.available}
                title={t.available ? `${t.calls} chamada(s) no mix` : (t.reason ?? "indisponível")}
              >
                <input
                  type="checkbox"
                  checked={selected.has(t.tool) && t.available}
                  disabled={!t.available}
                  onChange={() => toggle(t.tool)}
                />
                {t.tool}
              </label>
            ))}
          </div>
        ))}
      </fieldset>

      {parsed.errors.length > 0 && (
        <ul className="cobre-form-errors" role="alert">
          {parsed.errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}

      <button
        type="submit"
        className="cobre-btn cobre-btn-primary"
        disabled={disabled || parsed.body === null}
        title="Sobe um servidor MCP por cliente e chama as tools do mix pelo tempo informado"
      >
        ▶ Iniciar carga
      </button>
    </form>
  );
}
