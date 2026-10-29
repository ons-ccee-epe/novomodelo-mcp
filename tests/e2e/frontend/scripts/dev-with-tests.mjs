/**
 * Orquestrador: roda os testes E2E e SO ENTAO sobe o Vite.
 *
 * O dashboard consome os JSON gravados pelas baterias (tests/e2e/results/*).
 *
 * Fluxo:
 *   1. Executa `python -m tests.e2e.queries.run_queries` na raiz do novomodelo-mcp.
 *      A execucao de agente so acontece pelo executor em container; fora dele o
 *      comando recusa e o script segue.
 *   2. Conta as baterias em results/index.json; sem nenhuma, avisa.
 *   3. Faz spawn do Vite (vite), com ou sem baterias.
 *
 * Flags:
 *   --skip-tests   Nao roda a suite; conta as baterias e sobe o painel.
 *   --            Tudo apos `--` e repassado ao run_queries
 *                 (ex.: npm run dev:tests -- --tags bridge --parallel 4).
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { readFile, access } from "node:fs/promises";

const here = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(here, "..");
// tests/e2e/frontend -> tests/e2e -> tests -> <raiz do novomodelo-mcp>
const projectRoot = resolve(frontendDir, "..", "..", "..");
const indexJson = resolve(frontendDir, "..", "results", "index.json");

const PY = process.env.PYTHON ?? "python";

const rawArgs = process.argv.slice(2);
const skipTests = rawArgs.includes("--skip-tests");
const passthroughIdx = rawArgs.indexOf("--");
const testArgs = passthroughIdx >= 0 ? rawArgs.slice(passthroughIdx + 1) : [];

function log(msg) {
  process.stdout.write(`[dev-with-tests] ${msg}\n`);
}

/** Roda um comando herdando stdio; resolve com o exit code (nunca rejeita). */
function run(cmd, args, opts = {}) {
  return new Promise((resolveRun) => {
    const child = spawn(cmd, args, { stdio: "inherit", shell: false, ...opts });
    child.on("error", (err) => {
      log(`falha ao executar ${cmd}: ${err.message}`);
      resolveRun(-1);
    });
    child.on("close", (code) => resolveRun(code ?? -1));
  });
}

/** Le results/index.json e devolve quantas baterias existem (0 se ausente). */
async function countBatches() {
  try {
    await access(indexJson);
    const raw = await readFile(indexJson, "utf-8");
    const data = JSON.parse(raw);
    return Array.isArray(data.batches) ? data.batches.length : 0;
  } catch {
    return 0;
  }
}

async function main() {
  const before = await countBatches();

  if (!skipTests) {
    log(`rodando a suite E2E em ${projectRoot} ...`);
    const code = await run(
      PY,
      ["-m", "tests.e2e.queries.run_queries", ...testArgs],
      { cwd: projectRoot },
    );
    if (code !== 0) {
      // run_queries retorna 1 quando ha testes falhando — isso NAO e motivo
      // para nao abrir o dashboard (a bateria foi gravada mesmo assim).
      // So tratamos como bloqueio quando NAO ha nenhuma bateria para mostrar.
      log(`run_queries terminou com codigo ${code} (testes falhando ou CLI ausente).`);
    }
  } else {
    log("--skip-tests: pulando a execucao da suite.");
  }

  const after = await countBatches();
  if (after === 0) {
    log("aviso: nenhuma bateria em tests/e2e/results/; o painel abre sem baterias.");
  } else if (!skipTests && after === before) {
    log(`aviso: nenhuma bateria nova foi gravada; abrindo com as ${after} existentes.`);
  } else {
    log(`${after} bateria(s) disponivel(is). Subindo o dashboard...`);
  }

  // Sobe o Vite (mesma pasta). Repassa host/port definidos no vite.config.ts.
  const viteBin = resolve(frontendDir, "node_modules", ".bin", process.platform === "win32" ? "vite.cmd" : "vite");
  const code = await run(viteBin, [], { cwd: frontendDir });
  process.exit(code === -1 ? 1 : code);
}

main();
