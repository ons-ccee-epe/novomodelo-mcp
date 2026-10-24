import { useMemo } from "react";

import type { BatchResult, MetricsHistoryRecord } from "@/shared/types";
import { computeAlerts } from "../alertRules";

interface Props {
  batch: BatchResult;
  history: MetricsHistoryRecord[];
  baseline: BatchResult | null;
}

/** Banner de saúde da bateria (regras em alertRules). */
export function AlertBanner({ batch, history, baseline }: Props) {
  const alerts = useMemo(
    () => computeAlerts(batch, history, baseline),
    [batch, history, baseline],
  );

  if (alerts.length === 0) {
    return (
      <div className="cobre-banner" data-kind="healthy">
        ✓ Sistema saudável — nenhum alerta ativo
      </div>
    );
  }

  const kind = alerts.some((a) => a.level === "critical") ? "critical" : "warning";
  return (
    <div className="cobre-banner" data-kind={kind}>
      {alerts.map((a) => (
        <div key={a.message}>{a.message}</div>
      ))}
    </div>
  );
}
