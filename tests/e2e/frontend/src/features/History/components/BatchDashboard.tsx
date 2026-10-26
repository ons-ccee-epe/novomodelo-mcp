import { useEffect, useMemo, useState, type ReactNode } from "react";

import { changes as diff, pickReference } from "@/shared/comparison";
import { conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { BatchCards } from "./BatchCards";
import { BatchHeader } from "./BatchHeader";
import { ChangesStrip } from "./ChangesStrip";
import { ConjuntoEvolution } from "./ConjuntoEvolution";
import { QuestionList, type Change } from "./QuestionList";

interface Props {
  batch: BatchResult;
  all: BatchResult[];
  baselines: Record<string, string>;
  launcherOnline: boolean;
  onToggleBaseline: (batch: BatchResult) => Promise<void>;
  onDownloadSummary?: () => void;
  charts?: ReactNode;
}

export function BatchDashboard({
  batch,
  all,
  baselines,
  launcherOnline,
  onToggleBaseline,
  onDownloadSummary,
  charts,
}: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const reference = useMemo(() => pickReference(batch, all, baselines), [batch, all, baselines]);
  const { broke, fixed } = useMemo(
    () => (reference ? diff(batch, reference.batch) : { broke: [], fixed: [] }),
    [batch, reference],
  );
  const changeById = useMemo(() => {
    const map = new Map<string, Change>();
    broke.forEach((id) => map.set(id, "broke"));
    fixed.forEach((id) => map.set(id, "fixed"));
    return map;
  }, [broke, fixed]);

  useEffect(() => {
    if (!openId) return;
    document
      .querySelector(`[data-question-id="${CSS.escape(openId)}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [openId]);

  const toggle = () => {
    setToggleError(null);
    onToggleBaseline(batch).catch((e: unknown) => {
      setToggleError(e instanceof Error ? e.message : String(e));
    });
  };

  return (
    <section className="cobre-batch-dashboard" aria-label="Dashboard da bateria">
      <BatchHeader
        batch={batch}
        isBaseline={baselines[conjuntoOf(batch)] === batch.batch_id}
        canToggle={launcherOnline}
        onToggleBaseline={toggle}
        onDownloadSummary={onDownloadSummary}
      />
      {toggleError && (
        <p role="alert" className="cobre-run-finished-error">
          {toggleError}
        </p>
      )}
      <ChangesStrip broke={broke} fixed={fixed} onSelect={setOpenId} />
      <BatchCards batch={batch} reference={reference} />
      {charts}
      <ConjuntoEvolution batch={batch} all={all} baselines={baselines} />
      <QuestionList
        results={batch.test_results}
        changes={changeById}
        openId={openId}
        onOpen={setOpenId}
      />
    </section>
  );
}
