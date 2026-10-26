import type { BatchResult } from "@/shared/types";
import { ChartCard } from "./ChartCard";
import { DiagnosticFunnel } from "./DiagnosticFunnel";
import { LatencyByQuestion } from "./LatencyByQuestion";
import { PassByGroup } from "./PassByGroup";
import { StatusDonut } from "./StatusDonut";
import { ToolsPerQuestion } from "./ToolsPerQuestion";
import { ToolUsage } from "./ToolUsage";

export function BatchCharts({ batch }: { batch: BatchResult }) {
  const file = (slug: string) => `${batch.batch_id}-${slug}.png`;
  return (
    <section className="cobre-section cobre-charts" aria-label="Gráficos do resumo">
      <ChartCard title="Status" fileName={file("status")}>
        <StatusDonut batch={batch} />
      </ChartCard>
      <ChartCard title="Tempo por pergunta" fileName={file("tempo-por-pergunta")}>
        <LatencyByQuestion batch={batch} />
      </ChartCard>
      <ChartCard title="Tools mais usadas" fileName={file("tools-mais-usadas")}>
        <ToolUsage batch={batch} />
      </ChartCard>
      <ChartCard title="Tools por pergunta" fileName={file("tools-por-pergunta")}>
        <ToolsPerQuestion batch={batch} />
      </ChartCard>
      <ChartCard title="Aprovação por grupo" fileName={file("aprovacao-por-grupo")}>
        <PassByGroup batch={batch} />
      </ChartCard>
      <ChartCard title="Funil" fileName={file("funil")}>
        <DiagnosticFunnel batch={batch} />
      </ChartCard>
    </section>
  );
}
