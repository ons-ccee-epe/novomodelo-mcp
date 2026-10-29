import type { BatchResult } from "@/shared/types";
import { ChartCard } from "@/shared/charts/ChartCard";
import { DiagnosticFunnel } from "./DiagnosticFunnel";
import { LatencyByQuestion } from "./LatencyByQuestion";
import { PassByGroup } from "./PassByGroup";
import { StatusDonut } from "./StatusDonut";
import { ToolsPerQuestion } from "./ToolsPerQuestion";
import { ToolUsage } from "./ToolUsage";

export function BatchCharts({ batch }: { batch: BatchResult }) {
  const file = (slug: string) => `${batch.batch_id}-${slug}.png`;
  return (
    <section
      className="nm-section nm-charts nm-charts-pairs"
      aria-label="Gráficos do resumo"
    >
      <ChartCard title="Status" fileName={file("status")}>
        <StatusDonut batch={batch} />
      </ChartCard>
      <ChartCard
        title="Tools por pergunta"
        fileName={file("tools-por-pergunta")}
      >
        <ToolsPerQuestion batch={batch} />
      </ChartCard>
      <ChartCard
        title="Tempo por pergunta"
        fileName={file("tempo-por-pergunta")}
        wide
      >
        <LatencyByQuestion batch={batch} />
      </ChartCard>
      <ChartCard
        title="Tools mais usadas"
        fileName={file("tools-mais-usadas")}
        wide
      >
        <ToolUsage batch={batch} />
      </ChartCard>
      <ChartCard
        title="Aprovação por grupo"
        fileName={file("aprovacao-por-grupo")}
      >
        <PassByGroup batch={batch} />
      </ChartCard>
      <ChartCard title="Funil de diagnóstico" fileName={file("funil")}>
        <DiagnosticFunnel batch={batch} />
      </ChartCard>
    </section>
  );
}
