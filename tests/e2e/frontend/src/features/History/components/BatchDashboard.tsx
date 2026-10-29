import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { changes as diff, pickReference } from "@/shared/comparison";
import { downloadBlob, summaryPngBlob } from "@/shared/exportPng";
import type { BatchResult } from "@/shared/types";
import { BatchCharts } from "../charts/BatchCharts";
import { chartSvg } from "@/shared/charts/ChartCard";
import { formatDate } from "../format";
import { BatchOverview, BatchStats } from "./BatchCards";
import { BatchHeader, headerName } from "./BatchHeader";
import { ChangesStrip } from "./ChangesStrip";
import { ConjuntoEvolution } from "./ConjuntoEvolution";
import { QuestionList, type Change } from "./QuestionList";

const SEM_BASELINE: Record<string, string> = {};

interface Props {
  batch: BatchResult;
  /** Os lotes da mesma configuração e agente nas outras rodadas, para a variação e a evolução. */
  all: BatchResult[];
  /** Avisos sobre o que o registro não guarda ou o que não pôde ser carregado. */
  avisos?: string[];
  onDownloadSummary?: () => void;
  charts?: ReactNode;
}

export function BatchDashboard({
  batch,
  all,
  avisos = [],
  onDownloadSummary,
  charts,
}: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const rootRef = useRef<HTMLElement>(null);

  const reference = useMemo(() => pickReference(batch, all, SEM_BASELINE), [batch, all]);
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

  const downloadSummary = async () => {
    const root = rootRef.current;
    if (!root) return;
    setSummaryError(null);
    try {
      const cards = [...root.querySelectorAll("[data-stat]")].map((c) => ({
        label: c.querySelector("dt, .nm-card-label")?.textContent ?? "",
        value: c.querySelector("dd, .nm-rate")?.textContent ?? "",
      }));
      const charts = [...root.querySelectorAll<HTMLElement>("[data-chart-card]")].flatMap((c) => {
        const svg = chartSvg(c);
        if (!svg) return [];
        const title = c.querySelector("h4")?.textContent ?? "";
        return [{ title, svg, wide: c.dataset.wide === "true" }];
      });
      const title = `${headerName(batch)} — ${formatDate(batch.timestamp)} · ${batch.batch_id}`;
      downloadBlob(await summaryPngBlob(title, cards, charts), `${batch.batch_id}-resumo.png`);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section ref={rootRef} className="nm-batch-dashboard" aria-label="Dashboard da bateria">
      <BatchHeader batch={batch} onDownloadSummary={onDownloadSummary ?? downloadSummary} />
      {avisos.map((aviso) => (
        <p key={aviso} className="nm-muted" role="note">
          {aviso}
        </p>
      ))}
      {[summaryError].map(
        (msg) =>
          msg && (
            <p key={msg} role="alert" className="nm-run-finished-error">
              {msg}
            </p>
          ),
      )}
      <ChangesStrip broke={broke} fixed={fixed} onSelect={setOpenId} />
      <BatchOverview batch={batch} reference={reference} />
      <ConjuntoEvolution batch={batch} all={all} baselines={SEM_BASELINE} />
      <BatchStats batch={batch} />
      {charts ?? <BatchCharts batch={batch} />}
      <QuestionList
        results={batch.test_results}
        changes={changeById}
        openId={openId}
        onOpen={setOpenId}
      />
    </section>
  );
}
