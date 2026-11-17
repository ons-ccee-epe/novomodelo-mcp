/**
 * Orquestrador: roda uma rodada da bateria e SO ENTAO sobe o launcher e o painel.
 *
 * O painel lê as rodadas do launcher (GET /api/rodadas); este script só encadeia a
 * rodada e `npm run dev:launcher`.
 *
 * Fluxo:
 *   1. Executa `python -m novomodelo_mcp_e2e rodar <args>` na raiz do repositório. A execução dos
 *      agentes só acontece pelo executor em container; sem ele o comando recusa e o
 *      script segue.
 *   2. Sobe o launcher e o Vite (scripts/dev-launcher.mjs).
 *
 * Flags:
 *   --skip-tests   Não roda a bateria; sobe o launcher e o painel.
 *   --             Tudo após `--` é repassado ao `rodar`
 *                  (ex.: npm run dev:tests -- --mcp sem --conjuntos tools).
 */
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(here, "..");
// e2e/frontend -> e2e -> <raiz do repositório>
const projectRoot = resolve(frontendDir, "..", "..");

const PY = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

const rawArgs = process.argv.slice(2);
const skipTests = rawArgs.includes("--skip-tests");
const passthroughIdx = rawArgs.indexOf("--");
const rodarArgs = passthroughIdx >= 0 ? rawArgs.slice(passthroughIdx + 1) : [];

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

async function main() {
  if (!skipTests) {
    log(`rodando a bateria em ${projectRoot} ...`);
    const code = await run(PY, ["-m", "novomodelo_mcp_e2e", "rodar", ...rodarArgs], { cwd: projectRoot });
    if (code !== 0) {
      // Rodada com falha ou executor ausente não impede abrir o painel com o que já existe.
      log(`rodar terminou com código ${code}; abrindo o painel mesmo assim.`);
    }
  } else {
    log("--skip-tests: pulando a rodada.");
  }

  log("subindo o launcher e o painel...");
  const code = await run(process.execPath, [resolve(here, "dev-launcher.mjs")], {
    cwd: frontendDir,
  });
  process.exit(code === -1 ? 1 : code);
}

main();
