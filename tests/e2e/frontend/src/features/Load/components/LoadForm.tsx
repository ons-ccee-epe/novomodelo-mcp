import { useEffect, useMemo, useState } from "react";

import type { ProviderId } from "@/services/launcherApi";
import type {
  AgentCatalog,
  CapacityQuery,
  LoadCapacity,
  LoadLimits,
  LoadMode,
  LoadToolInfo,
  StartLoadBody,
} from "@/services/loadApi";
import { ProviderSelect } from "@/shared/components/ProviderSelect";
import { AgentCasePicker, type CaseScope } from "./AgentCasePicker";
import { LoadCapacityHint } from "./LoadCapacityHint";
import { ToolMixPicker } from "./ToolMixPicker";

export interface LoadFormValues {
  /** Ausente = tools. */
  mode?: LoadMode;
  concurrency: string;
  duration: string;
  iterations: string;
  timeout: string;
  tools: ReadonlySet<string>;
  provider?: ProviderId | null;
  scope?: CaseScope;
  group?: string | null;
  caseId?: string | null;
}

export interface ParsedLoadForm {
  body: StartLoadBody | null;
  /** Bloqueiam o envio. */
  errors: string[];
  /** Avisam, mas não bloqueiam. */
  warnings: string[];
}

export interface ParseContext {
  agent?: AgentCatalog | null;
  /** Capacidade do modo/provedor escolhidos; sem ela, só o teto rígido vale. */
  capacity?: LoadCapacity | null;
}

function parseNumber(raw: string): number | null {
  const text = raw.trim();
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : Number.NaN;
}

function parseInteger(raw: string): number | null {
  const value = parseNumber(raw);
  return value !== null && Number.isInteger(value) ? value : null;
}

/**
 * Tools que o POST deve mandar: ``null`` (mix padrão) só quando o conjunto escolhido é
 * exatamente o das tools ``available && default``; em qualquer outro caso, a lista explícita
 * (só das disponíveis, na ordem do catálogo).
 */
export function toolsSelection(
  selected: ReadonlySet<string>,
  tools: LoadToolInfo[],
): string[] | null {
  const chosen = tools.filter((t) => t.available && selected.has(t.tool)).map((t) => t.tool);
  const defaults = defaultTools(tools);
  const isDefault = chosen.length === defaults.size && chosen.every((t) => defaults.has(t));
  return isDefault ? null : chosen;
}

/** Um launcher anterior ao campo ``default`` não o manda: aí toda tool disponível é do padrão. */
function defaultTools(tools: LoadToolInfo[]): Set<string> {
  return new Set(tools.filter((t) => t.available && t.default !== false).map((t) => t.tool));
}

/** Provedor, casos elegíveis e escopo do modo agente; acrescenta os erros que achar. */
function agentScopeOf(
  values: LoadFormValues,
  agent: AgentCatalog | null,
  errors: string[],
): Pick<StartLoadBody, "case_id" | "group"> {
  if (!agent) {
    errors.push("O modo agente não está disponível.");
    return {};
  }
  const installed = agent.providers.some((p) => p.installed && p.id === values.provider);
  if (!installed) errors.push("Nenhum provedor de IA instalado (kiro-cli ou claude).");

  const eligible = agent.cases.filter((c) => c.available);
  const scope = values.scope ?? "all";
  if (scope === "group") {
    if (!values.group) errors.push("Escolha um grupo.");
    else if (!eligible.some((c) => c.group === values.group)) {
      errors.push(`O grupo ${values.group} não tem casos elegíveis.`);
    }
    return { group: values.group ?? null };
  }
  if (scope === "case") {
    if (!eligible.some((c) => c.id === values.caseId)) errors.push("Escolha um caso.");
    return { case_id: values.caseId ?? null };
  }
  if (eligible.length === 0) errors.push("Nenhum caso elegível para a carga.");
  return {};
}

/**
 * Valida o formulário contra os limites do launcher e monta o corpo do POST, só com os
 * campos do modo. Em tools, com exatamente as tools do mix padrão marcadas, envia
 * ``tools: null``; com qualquer outro conjunto, a lista explícita. Acima do teto rígido do modo é erro; acima do recomendado, só aviso.
 */
export function parseLoadForm(
  values: LoadFormValues,
  toolsLimits: LoadLimits,
  tools: LoadToolInfo[],
  context: ParseContext = {},
): ParsedLoadForm {
  const errors: string[] = [];
  const warnings: string[] = [];
  const mode = values.mode ?? "tools";
  const agent = context.agent ?? null;
  const limits = mode === "agent" && agent ? agent.limits : toolsLimits;

  const concurrency = parseNumber(values.concurrency);
  if (
    concurrency === null ||
    !Number.isInteger(concurrency) ||
    concurrency < limits.min_concurrency ||
    concurrency > limits.max_concurrency
  ) {
    errors.push(
      `Sessões simultâneas deve ser um inteiro de ${limits.min_concurrency} a ${limits.max_concurrency}.`,
    );
  } else if (context.capacity && concurrency > context.capacity.recommended) {
    warnings.push(
      `Acima do recomendado (≈ ${context.capacity.recommended}): a máquina pode saturar e distorcer a medição.`,
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
    errors.push(`Iterações por sessão deve ser um inteiro de 1 a ${limits.max_iterations}.`);
  }

  const timeout = parseNumber(values.timeout);
  if (
    timeout !== null &&
    (Number.isNaN(timeout) || timeout <= 0 || timeout > limits.max_timeout_seconds)
  ) {
    errors.push(`Timeout deve ficar entre 0 e ${limits.max_timeout_seconds} s.`);
  }

  if (mode === "agent") {
    const scope = agentScopeOf(values, agent, errors);
    if (errors.length > 0) return { body: null, errors, warnings };
    return {
      errors,
      warnings,
      body: {
        mode: "agent",
        concurrency: concurrency as number,
        duration_seconds: duration as number,
        iterations,
        timeout_seconds: timeout,
        provider: values.provider as ProviderId,
        ...scope,
      },
    };
  }

  const chosen = toolsSelection(values.tools, tools);
  const hasAny = tools.some((t) => t.available && values.tools.has(t.tool));
  if (!hasAny) errors.push("Escolha ao menos uma tool.");

  if (errors.length > 0) return { body: null, errors, warnings };
  return {
    errors,
    warnings,
    body: {
      concurrency: concurrency as number,
      duration_seconds: duration as number,
      iterations: iterations,
      tools: chosen,
      timeout_seconds: timeout,
    },
  };
}

interface Props {
  tools: LoadToolInfo[];
  limits: LoadLimits;
  disabled: boolean;
  onStart: (body: StartLoadBody) => void;
  /** Sem o catálogo do agente, só o modo tools fica disponível. */
  agent?: AgentCatalog | null;
  agentError?: string | null;
  capacity?: LoadCapacity | null;
  capacityError?: string | null;
  onRequestCapacity?: (
    mode: LoadMode,
    provider: ProviderId | null,
    selection: CapacityQuery,
  ) => void;
}

function groupTools(tools: LoadToolInfo[]): Array<[string, LoadToolInfo[]]> {
  const groups = new Map<string, LoadToolInfo[]>();
  for (const tool of tools) groups.set(tool.group, [...(groups.get(tool.group) ?? []), tool]);
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function defaultProvider(agent: AgentCatalog | null): ProviderId | null {
  if (!agent) return null;
  const installed = agent.providers.filter((p) => p.installed);
  const preferred = installed.find((p) => p.id === agent.defaultProvider);
  return (preferred ?? installed[0])?.id ?? null;
}

function tokenWarning(label: string, sessions: number | null, iterations: number | null): string {
  const base = `O modo agente consome tokens do provedor (${label}): o gasto cresce com sessões × casos.`;
  if (iterations !== null && iterations >= 1) {
    return sessions !== null && sessions >= 1
      ? `${base} Com ${iterations} iteração(ões) por sessão: até ${sessions} × ${iterations} = ${sessions * iterations} execuções.`
      : `${base} Cada sessão roda no máximo ${iterations} iteração(ões).`;
  }
  return `${base} Sem iterações definidas, o gasto é limitado pela duração.`;
}

const MODE_HINT: Record<LoadMode, string> = {
  tools:
    "Cada sessão sobe o seu próprio servidor MCP e chama as tools do mix, sem LLM. A subida dos servidores é medida à parte, fora da latência.",
  agent:
    "Cada sessão roda em laço os casos do cases.yaml num provedor de IA (consome tokens). A latência é a do caso inteiro, com a subida do agente.",
};

/**
 * Parâmetros da carga: modo (tools diretas ou casos por agente), sessões simultâneas,
 * duração (ou iterações), timeout e o que rodar (tools do mix ou casos do agente).
 */
export function LoadForm({
  tools,
  limits,
  disabled,
  onStart,
  agent = null,
  agentError = null,
  capacity = null,
  capacityError = null,
  onRequestCapacity,
}: Props) {
  const [mode, setMode] = useState<LoadMode>("tools");
  const [concurrency, setConcurrency] = useState("2");
  const [duration, setDuration] = useState("30");
  const [iterations, setIterations] = useState("");
  const [callTimeout, setCallTimeout] = useState(String(limits.default_timeout_seconds ?? ""));
  const [caseTimeout, setCaseTimeout] = useState("");
  const [chosenProvider, setChosenProvider] = useState<ProviderId | null>(null);
  const [scope, setScope] = useState<CaseScope>("all");
  const [group, setGroup] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  // Começa no mix padrão: as que gravam ou são pesadas só entram se a pessoa marcar.
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => defaultTools(tools));

  const barred = useMemo(() => tools.filter((t) => t.barred), [tools]);
  const groups = useMemo(() => groupTools(tools.filter((t) => !t.barred)), [tools]);
  const isAgent = mode === "agent";
  const provider = chosenProvider ?? defaultProvider(agent);
  const activeLimits = isAgent && agent ? agent.limits : limits;

  // O custo por sessão depende do que roda (pesada x leve, grava ou não): a seleção entra no
  // pedido. Chave em texto para o efeito só refazer o pedido quando a seleção muda de fato.
  const toolsKey = useMemo(
    () => (toolsSelection(selected, tools) ?? []).join(","),
    [selected, tools],
  );
  const capacityQuery = useMemo<CapacityQuery>(() => {
    if (!isAgent) return { tools: toolsKey ? toolsKey.split(",") : null };
    if (scope === "case") return { caseId };
    if (scope === "group") return { group };
    return {};
  }, [isAgent, toolsKey, scope, group, caseId]);

  // A memória livre é um instantâneo: pedir de novo ao trocar de modo, provedor ou seleção.
  useEffect(() => {
    onRequestCapacity?.(mode, mode === "agent" ? provider : null, capacityQuery);
  }, [mode, provider, capacityQuery, onRequestCapacity]);

  const capacityApplies =
    capacity !== null &&
    capacity.mode === mode &&
    (!isAgent || !provider || capacity.provider === provider);
  const shownCapacity = capacityApplies ? capacity : null;

  const parsed = parseLoadForm(
    {
      mode,
      concurrency,
      duration,
      iterations,
      timeout: isAgent ? caseTimeout : callTimeout,
      tools: selected,
      provider,
      scope,
      group,
      caseId,
    },
    limits,
    tools,
    { agent, capacity: shownCapacity },
  );
  const providerLabel = agent?.providers.find((p) => p.id === provider)?.label ?? "provedor";

  function toggle(tool: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tool)) next.delete(tool);
      else next.add(tool);
      return next;
    });
  }

  /** "todas" marca todas as disponíveis, inclusive as que gravam e as pesadas. */
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
      <section className="cobre-panel">
        <h2 className="cobre-panel-title">Configurar carga</h2>
        <div className="cobre-form-grid">
          <div className="cobre-field">
            <label htmlFor="load-mode" className="cobre-field-label">
              Modo
            </label>
            <select
              id="load-mode"
              className="cobre-select"
              value={mode}
              onChange={(e) => setMode(e.target.value as LoadMode)}
              disabled={disabled}
            >
              <option value="tools">Servidor MCP (tools, sem IA)</option>
              <option value="agent" disabled={!agent}>
                Uso real (agente de IA, gasta tokens)
              </option>
            </select>
          </div>
          {isAgent && agent && (
            <ProviderSelect
              id="load-provider"
              providers={agent.providers}
              value={provider}
              onChange={setChosenProvider}
              disabled={disabled}
            />
          )}
          <div className="cobre-field">
            <label htmlFor="load-concurrency" className="cobre-field-label">
              Sessões simultâneas
            </label>
            <input
              id="load-concurrency"
              className="cobre-input"
              type="number"
              inputMode="numeric"
              min={activeLimits.min_concurrency}
              max={activeLimits.max_concurrency}
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
              min={activeLimits.min_duration_seconds}
              max={activeLimits.max_duration_seconds}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className="cobre-field">
            <label htmlFor="load-iterations" className="cobre-field-label">
              Iterações por sessão (opcional)
            </label>
            <input
              id="load-iterations"
              className="cobre-input"
              type="number"
              min={1}
              max={activeLimits.max_iterations}
              placeholder="sem limite"
              value={iterations}
              onChange={(e) => setIterations(e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className="cobre-field">
            <label htmlFor="load-timeout" className="cobre-field-label">
              {isAgent ? "Timeout por caso (s, opcional)" : "Timeout por chamada (s)"}
            </label>
            <input
              id="load-timeout"
              className="cobre-input"
              type="number"
              min={0}
              max={activeLimits.max_timeout_seconds}
              placeholder={isAgent ? "o de cada caso" : undefined}
              value={isAgent ? caseTimeout : callTimeout}
              onChange={(e) => (isAgent ? setCaseTimeout : setCallTimeout)(e.target.value)}
              disabled={disabled}
            />
          </div>
        </div>
        <p className="cobre-muted cobre-mode-hint">{MODE_HINT[mode]}</p>
        {!agent && agentError && (
          <div className="cobre-muted cobre-load-note">Modo agente indisponível: {agentError}</div>
        )}

        {onRequestCapacity && <LoadCapacityHint capacity={shownCapacity} error={capacityError} />}
      </section>
      {parsed.warnings.map((message) => (
        <div key={message} className="cobre-banner" data-kind="warning">
          {message}
        </div>
      ))}

      {isAgent && agent && (
        <>
          <div className="cobre-banner" data-kind="warning">
            {tokenWarning(providerLabel, parseInteger(concurrency), parseInteger(iterations))}
          </div>
          <AgentCasePicker
            cases={agent.cases}
            scope={scope}
            group={group}
            caseId={caseId}
            disabled={disabled}
            onScope={setScope}
            onGroup={setGroup}
            onCase={setCaseId}
          />
        </>
      )}

      {!isAgent && (
        <ToolMixPicker
          groups={groups}
          barred={barred}
          selected={selected}
          isDefault={toolsSelection(selected, tools) === null}
          disabled={disabled}
          onToggle={toggle}
          onAll={setAll}
          onDefault={() => setSelected(defaultTools(tools))}
        />
      )}

      {parsed.errors.length > 0 && (
        <ul className="cobre-form-errors" role="alert">
          {parsed.errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}

      <div className="cobre-form-actions">
        <button
          type="submit"
          className="cobre-btn cobre-btn-primary"
          disabled={disabled || parsed.body === null}
          title={
            isAgent
              ? "Sobe um agente por sessão e roda os casos em laço pelo tempo informado (consome tokens)"
              : "Sobe um servidor MCP por sessão e chama as tools do mix pelo tempo informado"
          }
        >
          ▶ Iniciar carga
        </button>
      </div>
    </form>
  );
}
