import { conjuntoColor, conjuntoOf, conjuntoTag, conjuntoTitle } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";

export function ConjuntoTag({ batch }: { batch: BatchResult }) {
  const conjunto = conjuntoOf(batch);
  return (
    <span
      className="cobre-tag"
      title={conjuntoTitle(batch)}
      style={{ "--tag-color": conjuntoColor(conjunto) } as React.CSSProperties}
    >
      {conjuntoTag(conjunto)}
    </span>
  );
}
