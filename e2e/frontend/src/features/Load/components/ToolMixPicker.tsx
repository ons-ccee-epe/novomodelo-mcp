import type { LoadToolInfo } from "@/services/loadApi";
import { LoadBadges } from "./LoadBadges";

interface Props {
  groups: Array<[string, LoadToolInfo[]]>;
  barred: LoadToolInfo[];
  selected: ReadonlySet<string>;
  /** A seleção é exatamente o mix padrão. */
  isDefault: boolean;
  disabled: boolean;
  onToggle: (tool: string) => void;
  onAll: (on: boolean) => void;
  onDefault: () => void;
}

function summary(chosen: LoadToolInfo[], total: number, isDefault: boolean): string {
  const head = `${chosen.length} de ${total} tools`;
  if (isDefault) return `${head} · padrão: só leitura, sem as pesadas`;
  const writes = chosen.filter((t) => t.writes).length;
  const heavy = chosen.filter((t) => t.heavy).length;
  const extras = [
    writes > 0 ? `${writes} gravam` : null,
    heavy > 0 ? `${heavy} pesadas` : null,
  ].filter(Boolean);
  return [head, "personalizado", ...extras].join(" · ");
}

/** Tools que cada sessão chama em laço: um resumo, e a lista completa só ao personalizar. */
export function ToolMixPicker({
  groups,
  barred,
  selected,
  isDefault,
  disabled,
  onToggle,
  onAll,
  onDefault,
}: Props) {
  const listed = groups.flatMap(([, items]) => items);
  const available = listed.filter((t) => t.available);
  const chosen = available.filter((t) => selected.has(t.tool));
  const unavailable = listed.length - available.length;

  return (
    <fieldset className="nm-tool-picker nm-panel" disabled={disabled}>
      <legend className="nm-tool-picker-head">
        <span className="nm-panel-title">Tools do mix</span>
      </legend>
      <details className="nm-mix">
        <summary className="nm-mix-summary">
          <span>{summary(chosen, available.length, isDefault)}</span>
          {unavailable > 0 && (
            <span className="nm-muted" title="Faltam as fontes que essas tools leem">
              {unavailable} indisponíveis aqui
            </span>
          )}
          <span className="nm-mix-edit">Personalizar</span>
        </summary>
        <div className="nm-mix-body">
          <div className="nm-mix-actions">
            <button type="button" className="nm-btn nm-btn-sm" onClick={onDefault}>
              padrão
            </button>
            <button type="button" className="nm-btn nm-btn-sm" onClick={() => onAll(true)}>
              todas
            </button>
            <button type="button" className="nm-btn nm-btn-sm" onClick={() => onAll(false)}>
              nenhuma
            </button>
          </div>
          <div className="nm-muted nm-load-note">
            O mix padrão só tem tools que leem e são leves. Marque por sua conta as que gravam
            (rodam numa cópia das fixtures por sessão) ou as pesadas (sobem o bridge ou o solver).
          </div>
          {groups.map(([toolGroup, items]) => (
            <div key={toolGroup} className="nm-tool-group">
              <span className="nm-muted nm-tool-group-name">{toolGroup}</span>
              <div className="nm-tool-group-items">
                {items.map((t) => (
                  <span key={t.tool} className="nm-load-tool">
                    <label
                      className="nm-tag-option"
                      data-active={selected.has(t.tool) && t.available}
                      title={
                        t.available ? `${t.calls} chamada(s) no mix` : (t.reason ?? "indisponível")
                      }
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(t.tool) && t.available}
                        disabled={!t.available}
                        onChange={() => onToggle(t.tool)}
                      />
                      {t.tool}
                    </label>
                    <LoadBadges writes={t.writes} heavy={t.heavy} />
                  </span>
                ))}
              </div>
            </div>
          ))}
          {barred.length > 0 && (
            <details className="nm-load-excluded">
              <summary className="nm-summary-toggle">Fora da carga ({barred.length})</summary>
              <ul className="nm-tool-call-list">
                {barred.map((t) => (
                  <li key={t.tool}>
                    <code>{t.tool}</code> — {t.reason ?? "fora da carga"}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </details>
    </fieldset>
  );
}
