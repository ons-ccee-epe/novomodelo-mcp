export const STATUS_ICON: Record<string, string> = {
  pass: "✓",
  fail: "✗",
  partial: "◐",
  timeout: "⏱",
  skip: "⏭",
};

export const STATUS_LABEL: Record<string, string> = {
  pass: "Aprovada",
  partial: "Parcial",
  fail: "Falhou",
  timeout: "Timeout",
  skip: "Pulada",
};

export const UNKNOWN_STATUS_ICON = "?";

export function statusIcon(status: string): string {
  return STATUS_ICON[status] ?? UNKNOWN_STATUS_ICON;
}
