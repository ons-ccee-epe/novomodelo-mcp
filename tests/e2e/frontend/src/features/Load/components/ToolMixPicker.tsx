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
    <fieldset className="cobre-tool-picker cobre-panel" disabled={disabled}>
      <legend className="cobre-tool-picker-head">
        <span className="cobre-panel-title">Tools do mix</span>
      </legend>
      <details className="cobre-mix">
        <summary className="cobre-mix-summary">
          <span>{summary(chosen, available.length, isDefault)}</span>
          {unavailable > 0 && (
            <span className="cobre-muted" title="Faltam as fontes que essas tools leem">
              {unavailable} indisponíveis aqui
            </span>
          )}
          <span className="cobre-mix-edit">Personalizar</span>
        </summary>
        <div className="cobre-mix-body">
          <div className="cobre-mix-actions">
            <button type="button" className="cobre-btn cobre-btn-sm" onClick={onDefault}>
              padrão
            </button>
            <button type="button" className="cobre-btn cobre-btn-sm" onClick={() => onAll(true)}>
              todas
            </button>
            <button type="button" className="cobre-btn cobre-btn-sm" onClick={() => onAll(false)}>
              nenhuma
            </button>
          </div>
          <div className="cobre-muted cobre-load-note">
            O mix padrão só tem tools que leem e são leves. Marque por sua conta as que gravam
            (rodam numa cópia das fixtures por sessão) ou as pesadas (sobem o bridge ou o solver).
          </div>
          {groups.map(([toolGroup, items]) => (
            <div key={toolGroup} className="cobre-tool-group">
              <span className="cobre-muted cobre-tool-group-name">{toolGroup}</span>
              <div className="cobre-tool-group-items">
                {items.map((t) => (
                  <span key={t.tool} className="cobre-load-tool">
                    <label
                      className="cobre-tag-option"
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
            <details className="cobre-load-excluded">
              <summary className="cobre-summary-toggle">Fora da carga ({barred.length})</summary>
              <ul className="cobre-tool-call-list">
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
