"""Verificação de pré-requisitos para execução dos testes e2e."""

from __future__ import annotations

import importlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Diretório de fixtures
E2E_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = E2E_ROOT / "fixtures"


@dataclass
class PrerequisiteStatus:
    """Status de um pré-requisito."""

    name: str
    ok: bool
    message: str
    version: str | None = None


def check_novomodelo_bridge() -> PrerequisiteStatus:
    """Verifica se novomodelo-bridge CLI está disponível."""
    path = shutil.which("novomodelo-bridge")
    if path is None:
        return PrerequisiteStatus(
            name="novomodelo-bridge",
            ok=False,
            message="CLI não encontrada no PATH. Instale via: cargo install novomodelo-bridge",
        )

    try:
        result = subprocess.run(
            ["novomodelo-bridge", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return PrerequisiteStatus(
            name="novomodelo-bridge",
            ok=True,
            message=f"Encontrada em {path}",
            version=version,
        )
    except Exception as e:
        return PrerequisiteStatus(
            name="novomodelo-bridge",
            ok=False,
            message=f"Erro ao verificar versão: {e}",
        )


def check_novomodelo() -> PrerequisiteStatus:
    """Verifica se novomodelo CLI está disponível."""
    path = shutil.which("novomodelo")
    if path is None:
        return PrerequisiteStatus(
            name="novomodelo",
            ok=False,
            message="CLI não encontrada no PATH. Instale via: cargo install novomodelo",
        )

    try:
        result = subprocess.run(
            ["novomodelo", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return PrerequisiteStatus(
            name="novomodelo",
            ok=True,
            message=f"Encontrada em {path}",
            version=version,
        )
    except Exception as e:
        return PrerequisiteStatus(
            name="novomodelo",
            ok=False,
            message=f"Erro ao verificar versão: {e}",
        )


def check_novomodelo_mcp() -> PrerequisiteStatus:
    """Verifica se o pacote novomodelo-mcp está instalado."""
    try:
        importlib.import_module("novomodelo_mcp.server")

        # Tenta obter versão
        try:
            from importlib.metadata import version

            ver = version("novomodelo-mcp")
        except Exception:
            ver = "unknown"

        return PrerequisiteStatus(
            name="novomodelo-mcp",
            ok=True,
            message="Pacote importado com sucesso",
            version=ver,
        )
    except ImportError as e:
        return PrerequisiteStatus(
            name="novomodelo-mcp",
            ok=False,
            message=f"Pacote não instalado: {e}. Instale via: pip install -e .",
        )


def check_fixtures() -> PrerequisiteStatus:
    """Verifica se as fixtures existem."""
    required_dirs = [
        "newave",
        "decomp",
    ]

    missing = []
    for d in required_dirs:
        path = FIXTURES_DIR / d
        if not path.exists():
            missing.append(d)
        elif not any(path.iterdir()):
            missing.append(f"{d} (vazio)")

    if missing:
        return PrerequisiteStatus(
            name="fixtures",
            ok=False,
            message=f"Diretórios faltando em {FIXTURES_DIR}: {', '.join(missing)}",
        )

    # Conta fixtures disponíveis
    count = 0
    for d in FIXTURES_DIR.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            count += len(list(d.iterdir()))

    return PrerequisiteStatus(
        name="fixtures",
        ok=True,
        message=f"Encontradas em {FIXTURES_DIR}",
        version=f"{count} casos",
    )


def check_prerequisites(target: str = "local", skip_cli: bool = False) -> bool:
    """Verifica todos os pré-requisitos.

    Args:
        target: "local" para modo local, URL para remoto
        skip_cli: Se True, pula verificação de novomodelo/novomodelo-bridge

    Returns:
        True se todos os pré-requisitos estão OK.
    """
    statuses = get_prerequisites_status(target, skip_cli=skip_cli)
    return all(s.ok for s in statuses)


def get_prerequisites_status(
    target: str = "local", skip_cli: bool = False
) -> list[PrerequisiteStatus]:
    """Obtém status de todos os pré-requisitos.

    Args:
        target: "local" para modo local, URL para remoto
        skip_cli: Se True, pula verificação de novomodelo/novomodelo-bridge

    Returns:
        Lista de PrerequisiteStatus.
    """
    statuses = []

    if target == "local":
        # Modo local: precisa do pacote novomodelo-mcp
        statuses.append(check_novomodelo_mcp())

        if not skip_cli:
            # CLIs opcionais se skip_cli=True
            statuses.append(check_novomodelo_bridge())
            statuses.append(check_novomodelo())
    else:
        # Modo remoto: apenas verifica conectividade (futuro)
        statuses.append(
            PrerequisiteStatus(
                name="remote",
                ok=False,
                message=f"Modo remoto não implementado: {target}",
            )
        )

    # Fixtures são sempre necessárias
    statuses.append(check_fixtures())

    return statuses


def print_prerequisites_status(target: str = "local", skip_cli: bool = False) -> None:
    """Imprime status dos pré-requisitos formatado.

    Args:
        target: "local" para modo local, URL para remoto
        skip_cli: Se True, pula verificação de novomodelo/novomodelo-bridge
    """
    statuses = get_prerequisites_status(target, skip_cli=skip_cli)

    print("Pré-requisitos:")
    for s in statuses:
        icon = "✓" if s.ok else "✗"
        version_str = f" ({s.version})" if s.version else ""
        print(f"  {icon} {s.name}{version_str}")
        if not s.ok:
            print(f"      └─ {s.message}")

    if skip_cli:
        print("  ⚠ novomodelo/novomodelo-bridge: verificação pulada (--skip-cli-check)")
