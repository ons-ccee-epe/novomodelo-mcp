import type { ProviderId, ProviderInfo } from "@/services/launcherApi";

interface Props {
  providers: ProviderInfo[];
  selectedProvider: ProviderId | null;
  onSelectProvider: (p: ProviderId | null) => void;
  totalCases: number;
  disabled: boolean;
  noProvider: boolean;
  onRunAll: () => void;
}

/** Seletor de provedor de IA + disparo da esteira completa. */
export function LauncherControls({
  providers,
  selectedProvider,
  onSelectProvider,
  totalCases,
  disabled,
  noProvider,
  onRunAll,
}: Props) {
  return (
    <div className="cobre-launcher-row">
      <div className="cobre-launcher-provider">
        <label htmlFor="provider-select" className="cobre-muted">
          Provedor de IA
        </label>
        <select
          id="provider-select"
          value={selectedProvider ?? ""}
          onChange={(e) => onSelectProvider((e.target.value || null) as ProviderId | null)}
          disabled={disabled || noProvider}
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.installed}>
              {p.label}
              {p.installed ? "" : " (não instalado)"}
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className="cobre-btn cobre-btn-primary"
        onClick={onRunAll}
        disabled={disabled || noProvider}
        title="Roda a esteira completa de testes das tools MCP"
      >
        ▶ Esteira completa ({totalCases})
      </button>
    </div>
  );
}
