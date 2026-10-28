import { useMemo, useState } from "react";

import type { CaseMeta, RunResultItem } from "@/services/launcherApi";
import type { LoadCaseInfo } from "@/services/loadApi";
import { CaseList } from "@/features/Functional/components/launcher/CaseList";
import { LoadBadges } from "./LoadBadges";

export type CaseScope = "all" | "group" | "case";

interface Props {
  cases: LoadCaseInfo[];
  scope: CaseScope;
  group: string | null;
  caseId: string | null;
  disabled: boolean;
  onScope: (scope: CaseScope) => void;
  onGroup: (group: string | null) => void;
  onCase: (id: string | null) => void;
}

interface GroupCount {
  group: string;
  eligible: number;
  total: number;
  /** Entre os elegíveis. */
  writes: number;
  heavy: number;
}

/** " · 12 gravam · 10 pesados": só o que não é zero (sem sufixo, a contagem fica como era). */
export function describeWeight(writes: number, heavy: number): string {
  const parts: string[] = [];
  if (writes > 0) parts.push(`${writes} ${writes === 1 ? "grava" : "gravam"}`);
  if (heavy > 0) parts.push(`${heavy} ${heavy === 1 ? "pesado" : "pesados"}`);
  return parts.map((p) => ` · ${p}`).join("");
}

// A biblioteca só mostra resultados na esteira; aqui os casos nunca rodam por esta lista.
const NO_RESULTS = new Map<string, RunResultItem>();

export function countGroups(cases: LoadCaseInfo[]): GroupCount[] {
  const map = new Map<string, GroupCount>();
  for (const c of cases) {
    const entry = map.get(c.group) ?? {
      group: c.group,
      eligible: 0,
      total: 0,
      writes: 0,
      heavy: 0,
    };
    entry.total += 1;
    if (c.available) {
      entry.eligible += 1;
      if (c.writes) entry.writes += 1;
      if (c.heavy) entry.heavy += 1;
    }
    map.set(c.group, entry);
  }
  return [...map.values()].sort((a, b) => a.group.localeCompare(b.group));
}

function toCaseMeta(c: LoadCaseInfo): CaseMeta {
  return {
    id: c.id,
    query: c.query,
    expected_tool: c.expected_tool,
    expected_tools: c.expected_tools,
    tags: c.tags,
    timeout_s: c.timeout_s,
    requires: [],
  };
}

function CaseSummary({ item }: { item: LoadCaseInfo }) {
  return (
    <div className="nm-case-detail" aria-label="Caso escolhido">
      <code className="nm-detail-id">{item.id}</code>
      <dl className="nm-detail-meta">
        <div>
          <dt>Grupo</dt>
          <dd>{item.group}</dd>
        </div>
        <div>
          <dt>Tool esperada</dt>
          <dd>
            <code>{item.expected_tool ?? item.expected_tools?.join(" | ") ?? "—"}</code>
          </dd>
        </div>
        {(item.writes || item.heavy) && (
          <div>
            <dt>Custo</dt>
            <dd className="nm-load-selection">
              <LoadBadges writes={item.writes} heavy={item.heavy} />
            </dd>
          </div>
        )}
        {item.timeout_s !== null && (
          <div>
            <dt>Timeout</dt>
            <dd>{item.timeout_s}s</dd>
          </div>
        )}
      </dl>
      <pre className="nm-code">{item.query}</pre>
    </div>
  );
}

/** Escopo dos casos do modo agente: todos os elegíveis, um grupo ou um caso da biblioteca. */
export function AgentCasePicker({
  cases,
  scope,
  group,
  caseId,
  disabled,
  onScope,
  onGroup,
  onCase,
}: Props) {
  const [libraryGroup, setLibraryGroup] = useState<string | null>(null);

  const groups = useMemo(() => countGroups(cases), [cases]);
  const eligible = useMemo(() => cases.filter((c) => c.available), [cases]);
  const excluded = useMemo(() => cases.filter((c) => !c.available), [cases]);
  const library = useMemo(
    () => eligible.filter((c) => libraryGroup === null || c.group === libraryGroup),
    [eligible, libraryGroup],
  );
  const libraryMeta = useMemo(() => library.map(toCaseMeta), [library]);
  const chosen = eligible.find((c) => c.id === caseId) ?? null;
  const eligibleWrites = eligible.filter((c) => c.writes).length;
  const eligibleHeavy = eligible.filter((c) => c.heavy).length;

  return (
    <fieldset className="nm-tool-picker nm-panel" disabled={disabled}>
      <legend className="nm-tool-picker-head">
        <span className="nm-panel-title">Casos da carga</span>
      </legend>
      <div className="nm-form-row">
        <label className="nm-tag-option" data-active={scope === "all"}>
          <input
            type="radio"
            name="load-scope"
            checked={scope === "all"}
            onChange={() => onScope("all")}
          />
          Todos os casos ({eligible.length} elegíveis
          {describeWeight(eligibleWrites, eligibleHeavy)})
        </label>
        <label className="nm-tag-option" data-active={scope === "group"}>
          <input
            type="radio"
            name="load-scope"
            checked={scope === "group"}
            onChange={() => onScope("group")}
          />
          Grupo
        </label>
        <label className="nm-tag-option" data-active={scope === "case"}>
          <input
            type="radio"
            name="load-scope"
            checked={scope === "case"}
            onChange={() => onScope("case")}
          />
          Um caso
        </label>
      </div>

      {scope === "group" && (
        <div className="nm-field">
          <label htmlFor="load-group" className="nm-field-label">
            Grupo
          </label>
          <select
            id="load-group"
            className="nm-select"
            value={group ?? ""}
            onChange={(e) => onGroup(e.target.value || null)}
          >
            <option value="">-- Escolha um grupo --</option>
            {groups.map((g) => (
              <option key={g.group} value={g.group} disabled={g.eligible === 0}>
                {g.group} ({g.eligible}/{g.total} elegíveis
                {describeWeight(g.writes, g.heavy)})
              </option>
            ))}
          </select>
        </div>
      )}

      {scope === "case" && (
        <>
          <div className="nm-field">
            <label htmlFor="load-case-group" className="nm-field-label">
              Filtrar por grupo
            </label>
            <select
              id="load-case-group"
              className="nm-select"
              value={libraryGroup ?? ""}
              onChange={(e) => setLibraryGroup(e.target.value || null)}
            >
              <option value="">todos ({eligible.length})</option>
              {groups.map((g) => (
                <option key={g.group} value={g.group} disabled={g.eligible === 0}>
                  {g.group} ({g.eligible}
                  {describeWeight(g.writes, g.heavy)})
                </option>
              ))}
            </select>
          </div>
          <div className="nm-launcher-split">
            <CaseList
              cases={libraryMeta}
              selectedGroup={libraryGroup}
              selectedCaseId={caseId}
              runningCaseId={null}
              resultById={NO_RESULTS}
              onSelectCase={onCase}
            />
            {chosen ? (
              <CaseSummary item={chosen} />
            ) : (
              <div className="nm-no-data">Selecione um caso à esquerda.</div>
            )}
          </div>
        </>
      )}

      {excluded.length > 0 && (
        <details className="nm-load-excluded">
          <summary className="nm-summary-toggle">Fora da carga ({excluded.length})</summary>
          <ul className="nm-tool-call-list">
            {excluded.map((c) => (
              <li key={c.id}>
                <code>{c.id}</code> — {c.reason ?? "inelegível"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </fieldset>
  );
}
