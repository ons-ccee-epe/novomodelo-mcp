import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { changes as diff, pickReference } from "@/shared/comparison";
import { conjuntoOf } from "@/shared/conjunto";
import { downloadBlob, summaryPngBlob } from "@/shared/exportPng";
import type { BatchResult } from "@/shared/types";
import { BatchCharts } from "../charts/BatchCharts";
import { chartSvg } from "../charts/ChartCard";
import { formatDate } from "../format";
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
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const rootRef = useRef<HTMLElement>(null);

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

  const downloadSummary = async () => {
    const root = rootRef.current;
    if (!root) return;
    setSummaryError(null);
    try {
      const cards = [...root.querySelectorAll(".cobre-summary .cobre-card")].map((c) => ({
        label: c.querySelector(".cobre-card-label")?.textContent ?? "",
        value: c.querySelector(".cobre-card-value")?.textContent ?? "",
      }));
      const svgs = [...root.querySelectorAll("[data-chart-card]")]
        .map((c) => chartSvg(c))
        .filter((s): s is SVGSVGElement => s !== null);
      const title = `${formatDate(batch.timestamp)} · ${batch.batch_id}`;
      downloadBlob(await summaryPngBlob(title, cards, svgs), `${batch.batch_id}-resumo.png`);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section ref={rootRef} className="cobre-batch-dashboard" aria-label="Dashboard da bateria">
      <BatchHeader
        batch={batch}
        isBaseline={baselines[conjuntoOf(batch)] === batch.batch_id}
        canToggle={launcherOnline}
        onToggleBaseline={toggle}
        onDownloadSummary={onDownloadSummary ?? downloadSummary}
      />
      {[toggleError, summaryError].map(
        (msg) =>
          msg && (
            <p key={msg} role="alert" className="cobre-run-finished-error">
              {msg}
            </p>
          ),
      )}
      <ChangesStrip broke={broke} fixed={fixed} onSelect={setOpenId} />
      <BatchCards batch={batch} reference={reference} />
      {charts ?? <BatchCharts batch={batch} />}
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
