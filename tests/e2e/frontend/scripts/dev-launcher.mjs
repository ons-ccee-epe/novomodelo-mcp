/**
 * Sobe o launcher de dev (FastAPI) e o Vite juntos, num comando.
 *
 *   npm run dev:launcher
 *
 * - Lanca `python -m tests.e2e.launcher.serve` (porta 5175) a partir da raiz
 *   do novomodelo-mcp.
 * - Espera o /api/health responder.
 * - Sobe o Vite (porta 5174), cujo proxy /api -> 5175 ja esta no vite.config.ts.
 * - Encerra ambos ao receber Ctrl+C.
 *
 * Se o launcher nao subir (ex.: deps nao instaladas), avisa e sobe o Vite mesmo
 * assim; o painel le tudo do launcher, entao abre sem dados e mostra o erro de carga.
 */
import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(here, "..");
const projectRoot = resolve(frontendDir, "..", "..", ".."); // tests/e2e/frontend -> novomodelo-mcp

// Mesmo default do vite.config.ts; o proxy /api e o launcher precisam concordar.
const LAUNCHER_URL = new URL(process.env.VITE_LAUNCHER_URL || "http://127.0.0.1:5175");
const LAUNCHER_PORT = Number(LAUNCHER_URL.port);
const HEALTH_URL = new URL("/api/health", LAUNCHER_URL).toString();
const pythonCmd = process.platform === "win32" ? "python" : "python3";

const children = [];

// Com shell:true, c.kill() mata só o shell; no Windows o python, o Vite e os
// agentes em andamento ficariam órfãos. taskkill /T derruba a árvore inteira.
function killTree(child) {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/F", "/T", "/PID", String(child.pid)], { stdio: "ignore" });
  } else {
    child.kill();
  }
}

function shutdown(code = 0) {
  for (const c of children) {
    try {
      killTree(c);
    } catch {
      /* ignore */
    }
  }
  process.exit(code);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function startLauncher() {
  console.log(`[dev:launcher] subindo launcher FastAPI (${pythonCmd} -m tests.e2e.launcher.serve) ...`);
  const p = spawn(
    pythonCmd,
    ["-m", "tests.e2e.launcher.serve", "--port", String(LAUNCHER_PORT)],
    { cwd: projectRoot, stdio: "inherit", shell: true },
  );
  children.push(p);
  p.on("exit", (code) => {
    console.warn(`[dev:launcher] launcher encerrou (code=${code}).`);
  });
  return p;
}

async function waitForHealth(timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(HEALTH_URL);
      if (res.ok) return true;
    } catch {
      /* ainda subindo */
    }
    await new Promise((r) => setTimeout(r, 600));
  }
  return false;
}

function startVite() {
  console.log("[dev:launcher] subindo Vite (127.0.0.1:5174) ...");
  // No Windows, o binario do Vite e um .cmd (npx.cmd/vite.cmd). O Node moderno
  // recusa lancar .cmd direto (spawn EINVAL), entao usamos shell:true e um
  // comando em string — o shell resolve o .cmd. Em POSIX, shell:true tambem e
  // seguro aqui porque o comando e fixo (sem interpolacao de input do usuario).
  const p = spawn("npx vite", {
    cwd: frontendDir,
    stdio: "inherit",
    shell: true,
  });
  children.push(p);
  p.on("exit", (code) => shutdown(code ?? 0));
  return p;
}

async function main() {
  startLauncher();
  const healthy = await waitForHealth();
  if (healthy) {
    console.log("[dev:launcher] launcher no ar. Disparo de testes pela UI habilitado.");
  } else {
    console.warn(
      "[dev:launcher] launcher NAO respondeu o health a tempo.\n" +
        "  Verifique as deps: pip install -r tests/e2e/launcher/requirements.txt\n" +
        "  O Vite vai subir mesmo assim (o painel abre sem dados, pois le tudo do launcher).",
    );
  }
  startVite();
}

main().catch((e) => {
  console.error("[dev:launcher] erro:", e);
  shutdown(1);
});
