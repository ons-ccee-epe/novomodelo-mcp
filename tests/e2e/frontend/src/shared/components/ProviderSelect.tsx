import type { ProviderId, ProviderInfo } from "@/services/launcherApi";

interface Props {
  providers: ProviderInfo[];
  value: ProviderId | null;
  onChange: (p: ProviderId | null) => void;
  disabled?: boolean;
  id?: string;
}

/** Seletor do provedor de IA; os não instalados aparecem desabilitados. */
export function ProviderSelect({
  providers,
  value,
  onChange,
  disabled = false,
  id = "provider-select",
}: Props) {
  return (
    <div className="nm-launcher-provider">
      <label htmlFor={id} className="nm-field-label">
        Provedor de IA
      </label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(e) => onChange((e.target.value || null) as ProviderId | null)}
        disabled={disabled}
      >
        {providers.map((p) => (
          <option key={p.id} value={p.id} disabled={!p.installed}>
            {p.label}
            {p.installed ? "" : " (não instalado)"}
          </option>
        ))}
      </select>
    </div>
  );
}
