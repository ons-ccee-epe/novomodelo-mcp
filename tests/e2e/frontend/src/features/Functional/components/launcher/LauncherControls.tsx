import type { ProviderId, ProviderInfo } from "@/services/launcherApi";
import { ProviderSelect } from "@/shared/components/ProviderSelect";

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
    <div className="nm-launcher-row">
      <ProviderSelect
        providers={providers}
        value={selectedProvider}
        onChange={onSelectProvider}
        disabled={disabled || noProvider}
      />

      <button
        type="button"
        className="nm-btn nm-btn-primary"
        onClick={onRunAll}
        disabled={disabled || noProvider}
        title="Roda a esteira completa de testes das tools MCP"
      >
        ▶ Esteira completa ({totalCases})
      </button>
    </div>
  );
}
