/**
 * Orquestrador: roda os testes E2E e SO ENTAO sobe o Vite.
 *
 * Motivacao: o dashboard consome os JSON gravados pelos testes
 * (tests/e2e/results/*). Subir o dev server sem uma bateria de resultados
 * deixa a tela em branco. Este script garante que ha fonte de dados antes
 * de abrir o server.
 *
 * Fluxo:
 *   1. Executa `python -m tests.e2e.queries.run_queries` na raiz do novomodelo-mcp.
 *   2. Verifica que results/index.json existe e tem >= 1 bateria.
 *   3. So entao faz spawn do Vite (vite).
 *
 * Se os testes NAO puderem rodar (ex.: CLIs novomodelo/novomodelo-bridge ausentes) mas
 * JA existir pelo menos uma bateria em results/, o server sobe mesmo assim,
 * com um aviso — nunca bloqueia a visualizacao de resultados que ja existem.
 *
 * Flags:
 *   --skip-tests   Nao roda os testes; apenas valida que ha baterias e sobe.
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
    log("ERRO: nenhuma bateria em tests/e2e/results/ — nao ha o que mostrar.");
    log("Rode os testes com sucesso ao menos uma vez, ou verifique as CLIs novomodelo/novomodelo-bridge.");
    process.exit(1);
  }

  if (!skipTests && after === before) {
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
