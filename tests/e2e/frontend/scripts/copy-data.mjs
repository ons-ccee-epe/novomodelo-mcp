/**
 * Copia os resultados dos testes (tests/e2e/results e tests/e2e/metrics) para
 * dist/data/ depois do `vite build`, para que a SPA estatica os sirva como
 * assets. Em dev isso nao e necessario — o plugin resultsDataPlugin serve /data
 * direto do disco.
 *
 * Uso: node scripts/copy-data.mjs   (rodado pelo npm run build via postbuild,
 *      ou manualmente antes de publicar o dist/).
 */
import { cp, mkdir, readdir, access } from "node:fs/promises";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

const RESULTS_SRC = resolve(root, "..", "results");
const METRICS_SRC = resolve(root, "..", "metrics");
const DIST_DATA = resolve(root, "dist", "data");

async function exists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

async function copyBucket(src, destName) {
  if (!(await exists(src))) {
    console.warn(`[copy-data] origem ausente, pulando: ${src}`);
    return;
  }
  const dest = join(DIST_DATA, destName);
  await mkdir(dest, { recursive: true });
  const entries = await readdir(src);
  let copied = 0;
  for (const name of entries) {
    if (name.endsWith(".json") || name.endsWith(".jsonl")) {
      await cp(join(src, name), join(dest, name));
      copied += 1;
    }
  }
  console.log(`[copy-data] ${destName}: ${copied} arquivo(s)`);
}

await mkdir(DIST_DATA, { recursive: true });
await copyBucket(RESULTS_SRC, "results");
await copyBucket(METRICS_SRC, "metrics");
console.log(`[copy-data] concluído -> ${DIST_DATA}`);
