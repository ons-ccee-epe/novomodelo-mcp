import { Link } from "react-router-dom";

import { rateBand } from "@/features/History/format";
import { historyLoadPath } from "@/shared/constants/Routes";
import { indexEntryMode, type LoadIndexEntry } from "@/shared/types";
import { fmtCpm, fmtLoadId, fmtMs, fmtPercent, fmtRate } from "../format";

const ERROR_RATE_WARN = 0.05;

/** Até 5% de erro é atenção; acima, ruim. */
function errorBand(ratio: number): string {
  if (ratio === 0) return "good";
  return ratio <= ERROR_RATE_WARN ? "mid" : "bad";
}

/** Destaque do card: a aprovação no agente, a taxa de erro nas tools. */
function headline(entry: LoadIndexEntry) {
  const s = entry.summary;
  if (indexEntryMode(entry) === "agent") {
    const rate = typeof s.pass_rate === "number" ? s.pass_rate * 100 : null;
    return {
      value: rate === null ? "—" : `${Math.round(rate)}%`,
      band: rateBand(rate),
      caption: "aprovação",
      detail: `${fmtCpm(s.throughput_cpm)} · p95 ${fmtMs(s.p95_ms)}`,
    };
  }
  return {
    value: fmtPercent(s.error_rate),
    band: errorBand(s.error_rate),
    caption: "erro",
    detail: `${fmtRate(s.throughput_cps)} · p95 ${fmtMs(s.p95_ms)}`,
  };
}

interface Props {
  entry: LoadIndexEntry;
  selected: boolean;
}

export function LoadCard({ entry, selected }: Props) {
  const agent = indexEntryMode(entry) === "agent";
  const main = headline(entry);
  const { concurrency, duration_seconds: duration, provider } = entry.config;

  return (
    <li
      className="nm-batch-card nm-load-card"
      data-load-id={entry.load_id}
      aria-current={selected ? "true" : undefined}
    >
      <span className="nm-load-card-main">
        <Link className="nm-batch-link" to={historyLoadPath(entry.load_id)}>
          {fmtLoadId(entry.load_id)}
        </Link>
        <span className="nm-batch-tags">
          <span className="nm-pill" data-tone={agent ? "agent" : "tools"}>
            {agent ? `Agente${provider ? ` · ${provider}` : ""}` : "Tools"}
          </span>
          {entry.interrupted && (
            <span className="nm-pill" data-tone="partial">
              Parcial
            </span>
          )}
        </span>
        <span className="nm-batch-counts">
          {concurrency} sessões · {duration} s · {main.detail}
        </span>
      </span>
      <span className="nm-load-card-metric">
        <span className="nm-rate" data-band={main.band}>
          {main.value}
        </span>
        <span className="nm-muted">{main.caption}</span>
      </span>
    </li>
  );
}
