"""Cópia das fixtures por sessão (sandbox) para as cargas cuja seleção grava arquivos.

Com uma tool ou um caso que grava na seleção, cada sessão recebe, na sua pasta temporária,
uma cópia só das subárvores das fixtures que a seleção usa (``newave/novomodelo-mini``,
``results/sample_run``...) e uma ``scratch/`` vazia, com o mesmo layout das originais. Os
caminhos das chamadas e dos prompts passam a apontar para a cópia, e o
``NOVOMODELO_MCP_WORKSPACE`` do servidor da sessão é só a cópia: o path guard do servidor
(fail-closed) recusa as fixtures originais e a cópia de outra sessão. Sem nada que grave na
seleção não há cópia, e as sessões leem as fixtures originais.

A cópia é feita na subida da sessão (medida à parte, em ``copy_ms``) e apagada com a pasta
do run. O espaço em disco é conferido antes de copiar: ``SANDBOX_GROWTH`` reserva, além da
cópia, o que as tools gravam nela (deck convertido, relatórios, dashboard).

Todo servidor da carga roda com ``NOVOMODELO_MCP_MAX_JOBS=0``: ``run_start`` recusa runs, e
nenhuma sessão dispara o solver, nem um agente por conta própria.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.e2e.load.engine import LoadError
from tests.e2e.queries.mcp_workspace import WORKSPACE_ENV, workspace_roots

__all__ = [
    "DISK_HEADROOM",
    "MAX_JOBS_ENV",
    "SANDBOX_DIRNAME",
    "SANDBOX_GROWTH",
    "STATE_DIR_ENV",
    "TEMP_VARS",
    "SandboxPlan",
    "SessionSandbox",
    "ToolsSessions",
    "check_disk",
    "make_run_root",
    "plan_for",
    "plan_for_specs",
    "remove_tree",
    "sandbox_summary",
    "strings_in",
    "subtrees_in",
]

STATE_DIR_ENV = "NOVOMODELO_MCP_STATE_DIR"
MAX_JOBS_ENV = "NOVOMODELO_MCP_MAX_JOBS"
TEMP_VARS = ("TEMP", "TMP", "TMPDIR")
SANDBOX_DIRNAME = "fixtures"
SCRATCH_DIRNAME = "scratch"

# Além da cópia, o que as tools gravam nela: medido, uma conversão NEWAVE grava cerca do
# tamanho do caso de entrada; o dobro da cópia abrange conversão, relatórios e backups.
SANDBOX_GROWTH = 1.0
DISK_HEADROOM = 0.10

_MB = 1024 * 1024
_PATH_TAIL = r"[\\/]([^\s'\"?,;:()]+)"
_REMOVE_ATTEMPTS = 5
_REMOVE_PAUSE_S = 0.4


def strings_in(value: Any) -> Iterable[str]:
    """Todas as strings de um valor (argumentos de uma chamada, por exemplo)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_in(item)


def subtrees_in(texts: Iterable[str], fixtures: Path) -> set[str]:
    """Subárvores (``categoria/caso``) das fixtures citadas em ``texts`` que existem.

    Um caminho que não existe (``{FIXTURES}/nonexistent``) ou que a tool cria
    (``{FIXTURES}/scratch/...``) não vira subárvore: na cópia ele também não existe.
    """
    fixtures = Path(fixtures)
    patterns = [
        re.compile(re.escape(root) + _PATH_TAIL)
        for root in dict.fromkeys((str(fixtures), fixtures.as_posix()))
    ]
    found: set[str] = set()
    for text in texts:
        for pattern in patterns:
            for match in pattern.finditer(text):
                parts = [p for p in re.split(r"[\\/]", match.group(1)) if p][:2]
                if len(parts) < 2:
                    continue
                parts[1] = parts[1].rstrip(".")
                if parts[0] != SCRATCH_DIRNAME and fixtures.joinpath(*parts).is_dir():
                    found.add("/".join(parts))
    return found


def _tree_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.stat(os.path.join(dirpath, name)).st_size
            except OSError:
                continue
    return total


@dataclass(frozen=True)
class SandboxPlan:
    """O que cada sessão copia; ``enabled`` falso = sem cópia, as fixtures originais."""

    fixtures: Path
    subtrees: tuple[str, ...] = ()
    enabled: bool = False
    copy_bytes: int = 0

    @property
    def copy_mb(self) -> float:
        return self.copy_bytes / _MB

    @property
    def per_session_mb(self) -> float:
        """Disco por sessão: a cópia mais o que as tools gravam nela."""
        return self.copy_mb * (1 + SANDBOX_GROWTH)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "subtrees": list(self.subtrees),
            "copy_mb": self.copy_mb,
            "per_session_mb": self.per_session_mb if self.enabled else 0.0,
            "growth": SANDBOX_GROWTH,
        }


def plan_for(fixtures: str | Path, texts: Iterable[str], enabled: bool) -> SandboxPlan:
    """Plano de cópia: as subárvores citadas em ``texts``, só se a seleção grava (``enabled``)."""
    root = Path(fixtures).resolve()
    if not enabled:
        return SandboxPlan(fixtures=root)
    subtrees = tuple(sorted(subtrees_in(texts, root)))
    size = sum(_tree_bytes(root / subtree) for subtree in subtrees)
    return SandboxPlan(fixtures=root, subtrees=subtrees, enabled=True, copy_bytes=size)


def plan_for_specs(fixtures: str | Path, specs: Iterable[Any]) -> SandboxPlan:
    """Plano da cópia do modo tools: as subárvores das chamadas (``mix.CallSpec``), se alguma
    grava. Vale para o mix antes do pré-voo, que só tira chamadas."""
    specs = list(specs)
    texts = [text for spec in specs for text in strings_in(spec.arguments)]
    return plan_for(fixtures, texts, any(spec.writes for spec in specs))


def check_disk(
    plan: SandboxPlan,
    sessions: int,
    work_dir: str | Path,
    disk_usage: Callable[[str], Any] = shutil.disk_usage,
) -> None:
    """Recusa a carga se as cópias das sessões não cabem no disco da pasta do run.

    Raises:
        LoadError: Se ``sessions`` cópias (com a folga do que as tools gravam) passam do
            espaço livre menos ``DISK_HEADROOM``.
    """
    if not plan.enabled or plan.copy_bytes == 0:
        return
    free_mb = disk_usage(str(work_dir)).free / _MB
    needed_mb = plan.per_session_mb * sessions
    budget_mb = free_mb * (1 - DISK_HEADROOM)
    if needed_mb > budget_mb:
        raise LoadError(
            f"disco insuficiente para a cópia das fixtures por sessão: {sessions} × "
            f"{plan.per_session_mb:.0f} MB = {needed_mb:.0f} MB, livres {free_mb:.0f} MB em "
            f"{work_dir} (folga de {DISK_HEADROOM:.0%}); reduza as sessões ou a seleção"
        )


def remove_tree(path: Path) -> bool:
    """Apaga ``path`` inteiro, com novas tentativas: no Windows um processo recém-encerrado
    ainda segura arquivos por um instante. True se não sobrou nada."""
    for attempt in range(_REMOVE_ATTEMPTS):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        if attempt < _REMOVE_ATTEMPTS - 1:
            time.sleep(_REMOVE_PAUSE_S)
    return False


def make_run_root(work_dir: str | Path | None, prefix: str) -> Path:
    """Pasta temporária de um run, dentro de ``work_dir`` (ou do TEMP), com o caminho longo."""
    parent = None if work_dir is None else str(work_dir)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()


class SessionSandbox:
    """A cópia das fixtures de uma sessão; sem plano habilitado, aponta para as originais."""

    def __init__(self, plan: SandboxPlan, session_root: Path) -> None:
        self.plan = plan
        self.root = Path(session_root) / SANDBOX_DIRNAME if plan.enabled else plan.fixtures
        self.copy_seconds: float | None = None
        self.reset_skipped = 0
        self._files: dict[str, tuple[int, int]] = {}
        self._dirs: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self.plan.enabled

    def create(self) -> float:
        """Copia as subárvores e cria ``scratch/``; devolve os segundos gastos (0 sem cópia)."""
        if not self.enabled:
            return 0.0
        started = time.perf_counter()
        (self.root / SCRATCH_DIRNAME).mkdir(parents=True, exist_ok=True)
        for subtree in self.plan.subtrees:
            shutil.copytree(self.plan.fixtures / subtree, self.root / subtree)
        self._snapshot()
        self.copy_seconds = time.perf_counter() - started
        return self.copy_seconds

    def _snapshot(self) -> None:
        self._files.clear()
        self._dirs.clear()
        for dirpath, dirnames, filenames in os.walk(self.root):
            here = Path(dirpath).relative_to(self.root)
            for name in dirnames:
                self._dirs.add((here / name).as_posix())
            for name in filenames:
                stat = os.stat(os.path.join(dirpath, name))
                self._files[(here / name).as_posix()] = (stat.st_size, stat.st_mtime_ns)

    def workspace_roots(self) -> list[Path]:
        """Raízes do path guard da sessão: só a cópia ou, sem ela, as fixtures e seus links."""
        if self.enabled:
            return [self.root]
        return workspace_roots(self.plan.fixtures)

    def workspace_env(self) -> str:
        return os.pathsep.join(str(root) for root in self.workspace_roots())

    def rewrite(self, text: str) -> str:
        """Troca o caminho das fixtures originais pelo da cópia (nativo e com ``/``)."""
        if not self.enabled:
            return text
        original = self.plan.fixtures
        return text.replace(str(original), str(self.root)).replace(
            original.as_posix(), self.root.as_posix()
        )

    def reset(self) -> None:
        """Volta a cópia ao estado da subida: apaga o que foi criado e recopia o que mudou.

        Chamar só com a sessão parada (nenhum agente ou servidor dela em curso). Um arquivo
        que não pôde ser restaurado conta em ``reset_skipped`` e não interrompe a sessão.
        """
        if not self.enabled or not self._files:
            return
        seen: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(self.root):
            here = Path(dirpath).relative_to(self.root)
            for name in list(dirnames):
                relative = (here / name).as_posix()
                if relative not in self._dirs:
                    shutil.rmtree(Path(dirpath, name), ignore_errors=True)
                    dirnames.remove(name)
            for name in filenames:
                relative = (here / name).as_posix()
                seen.add(relative)
                self._restore_file(relative, Path(dirpath, name))
        for relative in self._files.keys() - seen:
            self._restore_file(relative, self.root / relative)

    def _restore_file(self, relative: str, path: Path) -> None:
        expected = self._files.get(relative)
        try:
            if expected is None:
                path.unlink(missing_ok=True)
                return
            if path.exists():
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) == expected:
                    return
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.plan.fixtures / relative, path)
        except OSError:
            # No Windows, o servidor do caso anterior pode ainda segurar o arquivo ao sair:
            # falhar aqui viraria erro do próximo caso, que nada tem a ver com o servidor.
            self.reset_skipped += 1

    def size_bytes(self) -> int:
        return _tree_bytes(self.root) if self.enabled and self.root.exists() else 0


def sandbox_summary(plan: SandboxPlan, sandboxes: Iterable[SessionSandbox]) -> dict[str, Any]:
    """Bloco ``sandbox`` do resultado: o plano, o tempo de cópia e o maior tamanho ao fim."""
    if not plan.enabled:
        return {"enabled": False}
    boxes = [box for box in sandboxes if box.copy_seconds is not None]
    copies = [box.copy_seconds * 1000.0 for box in boxes if box.copy_seconds is not None]
    finals = [box.size_bytes() / _MB for box in boxes]
    return {
        **plan.describe(),
        "sessions": len(boxes),
        "copy_ms_mean": sum(copies) / len(copies) if copies else None,
        "copy_ms_max": max(copies) if copies else None,
        "final_mb_max": max(finals) if finals else None,
    }


class ToolsSessions:
    """Pastas das sessões do modo tools (``-1`` é o pré-voo): TEMP, state dir e a cópia.

    O TEMP próprio evita que um servidor leia os schemas que outro ainda exporta, e o state
    dir próprio tira ``run_plan`` dos jobs e da calibração do usuário.
    """

    def __init__(self, run_root: Path, plan: SandboxPlan) -> None:
        self.run_root = Path(run_root)
        self.plan = plan
        self._sandboxes: dict[int, SessionSandbox] = {}
        self._lock = threading.Lock()

    def _folder(self, index: int) -> Path:
        return self.run_root / ("preflight" if index < 0 else f"s{index}")

    def prepare(self, index: int) -> float:
        """Cria as pastas da sessão e a cópia, uma vez por sessão; devolve os segundos da cópia."""
        with self._lock:
            if index in self._sandboxes:
                return 0.0
            sandbox = SessionSandbox(self.plan, self._folder(index))
            self._sandboxes[index] = sandbox
        for name in ("tmp", "mcp-state"):
            (self._folder(index) / name).mkdir(parents=True, exist_ok=True)
        return sandbox.create()

    def root(self, index: int) -> Path:
        """Raiz das fixtures que as chamadas da sessão usam (a cópia, se houver)."""
        sandbox = self._sandboxes.get(index)
        return sandbox.root if sandbox is not None else self.plan.fixtures

    def env(self, index: int) -> dict[str, str]:
        folder = self._folder(index)
        sandbox = self._sandboxes.get(index) or SessionSandbox(self.plan, folder)
        values = {
            STATE_DIR_ENV: str(folder / "mcp-state"),
            MAX_JOBS_ENV: "0",
            WORKSPACE_ENV: sandbox.workspace_env(),
        }
        values.update(dict.fromkeys(TEMP_VARS, str(folder / "tmp")))
        return values

    def release(self, index: int) -> None:
        """Apaga a pasta de uma sessão encerrada (o pré-voo), liberando o disco da cópia."""
        with self._lock:
            sandbox = self._sandboxes.pop(index, None)
        if sandbox is not None:
            remove_tree(self._folder(index))

    def summary(self) -> dict[str, Any]:
        with self._lock:
            sessions = [box for index, box in self._sandboxes.items() if index >= 0]
        return sandbox_summary(self.plan, sessions)

    def close(self) -> bool:
        """Apaga a pasta do run inteira; True se não sobrou nada."""
        return remove_tree(self.run_root)
