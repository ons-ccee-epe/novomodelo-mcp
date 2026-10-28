"""Detecção da máquina local: identidade, CPUs e RAM EFETIVOS. Stdlib pura, multiplataforma.

- CPUs: respeita afinidade do processo e cota de cgroup (Docker/K8s), não só o
  total do host. Em CPU HÍBRIDA (Apple Silicon, Intel 12ª+, ARM big.LITTLE)
  detecta os núcleos de PERFORMANCE: threads em núcleos de eficiência viram
  gargalo nas barreiras do SDDP (medido: 7 threads mais lento que 4 num 4P+4E).
- RAM: Windows (GlobalMemoryStatusEx), macOS (sysctl hw.memsize), Linux
  (/proc/meminfo), limitada pelo cgroup quando houver.
- Identidade: `machine_id` estável (independe de hostname, que muda com rede/VPN),
  exposto apenas como hash — nunca o identificador bruto do hardware.

Cada sonda é injetável em `detect_machine(...)` para testes determinísticos.
"""

from __future__ import annotations

import hashlib
import math
import os
import platform
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .subproc import NO_WINDOW

_GIB = 1024**3
_CGROUP = Path("/sys/fs/cgroup")


def system_tool(name: str, *dirs: str) -> str:
    """Caminho ABSOLUTO de uma ferramenta do sistema, independente do PATH.

    Clientes MCP costumam subir o servidor com um PATH mínimo (sem /usr/sbin no
    macOS, onde vivem `sysctl` e `ioreg`); sem isto a sonda falharia em silêncio.
    """
    for d in dirs:
        cand = Path(d) / name
        if cand.exists():
            return str(cand)
    return name


def _sysctl() -> str:
    return system_tool("sysctl", "/usr/sbin", "/sbin")


# ── parsers puros (testáveis em qualquer SO) ──────────────────────────────────


def parse_meminfo(text: str) -> int | None:
    """Extrai `MemTotal` (em bytes) do conteúdo de /proc/meminfo."""
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            try:
                value = int(parts[1])
            except (IndexError, ValueError):
                return None
            unit = parts[2].lower() if len(parts) > 2 else "kb"
            return value * 1024 if unit == "kb" else value
    return None


def parse_cpu_max(text: str) -> float | None:
    """cgroup v2 `cpu.max` ("quota período" ou "max período") -> nº de CPUs, ou None."""
    parts = text.split()
    if len(parts) != 2 or parts[0] == "max":
        return None
    try:
        quota, period = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return quota / period if quota > 0 and period > 0 else None


def parse_mem_limit(text: str) -> int | None:
    """cgroup `memory.max` / `memory.limit_in_bytes` -> bytes, ou None se ilimitado."""
    text = text.strip()
    if not text or text == "max":
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if 0 < value < 2**60 else None  # v1 usa ~2^63 como "ilimitado"


def parse_cpu_list(text: str) -> int:
    """Conta CPUs numa lista do kernel ("0-7,16-23" -> 16)."""
    n = 0
    for part in text.strip().split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        try:
            n += (int(hi) - int(lo) + 1) if hi else 1
        except ValueError:
            continue
    return n


def performance_from_classes(cores: list[tuple[int, int]]) -> int | None:
    """[(classe_de_eficiência, nº_lógicos)] -> lógicos na classe MAIS rápida.

    None se todos os núcleos são da mesma classe (CPU não híbrida).
    """
    classes = {c for c, _ in cores}
    if len(classes) <= 1:
        return None
    top = max(classes)
    return sum(n for c, n in cores if c == top)


def parse_win_cores(buf: bytes, ptr_size: int = 8) -> list[tuple[int, int]]:
    """Decodifica SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX (RelationProcessorCore).

    Layout por registro: Relationship(4) Size(4) | Flags(1) EfficiencyClass(1)
    Reserved(20) GroupCount(2) | GroupMask[GroupCount] (cada: Mask(ptr) Group(2)
    Reserved(6)), com o GroupMask alinhado em 8 -> início em +32.
    """
    cores: list[tuple[int, int]] = []
    off, step = 0, ptr_size + 8
    while off + 8 <= len(buf):
        rel = int.from_bytes(buf[off : off + 4], "little")
        size = int.from_bytes(buf[off + 4 : off + 8], "little")
        if size <= 0:
            break
        if rel == 0 and off + 32 <= len(buf):
            eff = buf[off + 9]
            groups = int.from_bytes(buf[off + 30 : off + 32], "little")
            logical = 0
            for g in range(groups):
                m = off + 32 + g * step
                logical += bin(int.from_bytes(buf[m : m + ptr_size], "little")).count("1")
            cores.append((eff, logical or 1))
        off += size
    return cores


def normalize_hostname(name: str | None) -> str:
    """Forma canônica p/ comparar hostnames: sem espaços, minúsculo, sem domínio."""
    return (name or "").strip().lower().split(".")[0]


# ── sondas do sistema ─────────────────────────────────────────────────────────


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _cgroup_cpu_limit() -> float | None:
    if (text := _read(_CGROUP / "cpu.max")) is not None:
        return parse_cpu_max(text)
    quota, period = (
        _read(_CGROUP / "cpu" / "cpu.cfs_quota_us"),
        _read(_CGROUP / "cpu" / "cpu.cfs_period_us"),
    )
    if quota and period:
        return parse_cpu_max(f"{quota.strip()} {period.strip()}".replace("-1 ", "max "))
    return None


def _cgroup_mem_limit() -> int | None:
    for f in (_CGROUP / "memory.max", _CGROUP / "memory" / "memory.limit_in_bytes"):
        if (text := _read(f)) is not None:
            return parse_mem_limit(text)
    return None


def detect_cpu_count() -> int:
    """CPUs utilizáveis por ESTE processo (afinidade + cota de cgroup)."""
    if hasattr(os, "process_cpu_count"):  # Python 3.13+
        n = os.process_cpu_count() or 1
    elif hasattr(os, "sched_getaffinity"):
        n = len(os.sched_getaffinity(0)) or 1
    else:
        n = os.cpu_count() or 1
    if sys.platform.startswith("linux") and (quota := _cgroup_cpu_limit()):
        n = min(n, max(1, math.floor(quota)))
    return n


def _sysctl_int(name: str) -> int | None:
    try:
        # argv fixa (ferramenta do SO + nome de chave interno), sem shell: nada vem do agente.
        out = subprocess.run(
            [_sysctl(), "-n", name],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            timeout=5,
            **NO_WINDOW,
        )
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _perf_cpus_macos() -> int | None:
    if (_sysctl_int("hw.nperflevels") or 1) < 2:
        return None
    return _sysctl_int("hw.perflevel0.logicalcpu")  # perflevel0 = performance


def _perf_cpus_linux() -> int | None:
    core = _read(Path("/sys/devices/cpu_core/cpus"))  # Intel híbrido (P-cores)
    if core and _read(Path("/sys/devices/cpu_atom/cpus")):
        return parse_cpu_list(core) or None
    caps = []  # ARM big.LITTLE
    for f in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpu_capacity")):
        try:
            caps.append(int((_read(f) or "").strip()))
        except ValueError:
            continue
    return performance_from_classes([(c, 1) for c in caps]) if caps else None


def _perf_cpus_windows() -> int | None:
    import ctypes

    try:
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        length = ctypes.c_ulong(0)
        k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(length))
        buf = ctypes.create_string_buffer(length.value)
        if not k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(length)):
            return None
    except (AttributeError, OSError):
        return None
    cores = parse_win_cores(buf.raw[: length.value], ctypes.sizeof(ctypes.c_void_p))
    return performance_from_classes(cores)


def detect_performance_cpus() -> int | None:
    """Nº de CPUs lógicas de PERFORMANCE em CPU híbrida; None se não híbrida."""
    try:
        if sys.platform == "win32":
            return _perf_cpus_windows()
        if sys.platform == "darwin":
            return _perf_cpus_macos()
        if sys.platform.startswith("linux"):
            return _perf_cpus_linux()
    except Exception:  # noqa: BLE001 - sonda best-effort: nunca derruba o plano
        return None
    return None


def _ram_windows() -> int | None:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return None
    return int(st.ullTotalPhys) if ok else None


def _ram_macos() -> int | None:
    return _sysctl_int("hw.memsize")


def _ram_posix_sysconf() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return None


def detect_ram_bytes() -> int | None:
    """RAM utilizável: física, limitada pelo cgroup (Linux) quando houver."""
    if sys.platform == "win32":
        return _ram_windows()
    if sys.platform == "darwin":
        return _ram_macos() or _ram_posix_sysconf()
    text = _read(Path("/proc/meminfo"))
    ram = (parse_meminfo(text) if text else None) or _ram_posix_sysconf()
    limit = _cgroup_mem_limit()
    if limit and (ram is None or limit < ram):
        return limit
    return ram


def _raw_machine_id() -> str | None:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            return None
    if sys.platform == "darwin":
        try:
            # argv fixa, sem shell: nada vem do agente.
            out = subprocess.run(
                [
                    system_tool(
                        "ioreg", "/usr/sbin"
                    ),  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    "-rd1",
                    "-c",
                    "IOPlatformExpertDevice",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                **NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out.stdout or "")
        return m.group(1) if m else None
    for f in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        if (text := _read(f)) and text.strip():
            return text.strip()
    return None


def detect_machine_id() -> str:
    """Hash estável da máquina (sha256 truncado).

    Fallback: MAC da interface; se o SO não expõe nenhum, `uuid.getnode()` inventa
    um aleatório (bit multicast ligado) — aí cai para o hostname normalizado.
    """
    raw = _raw_machine_id()
    if not raw:
        node = uuid.getnode()
        raw = (
            f"node-{node:012x}"
            if not node & (1 << 40)
            else f"host-{normalize_hostname(socket.gethostname())}"
        )
    return hashlib.sha256(f"{raw}".encode()).hexdigest()[:16]


_UNSET: Any = object()


def detect_machine(
    *,
    hostname: str | None = None,
    cpu_count: int | None = None,
    ram_bytes: int | None = None,
    machine_id: str | None = None,
    performance_cpus: int | None = _UNSET,
) -> dict[str, Any]:
    """Retrato da máquina. Valores passados explicitamente têm prioridade (mock/teste)."""
    host = hostname if hostname is not None else socket.gethostname()
    cores = cpu_count if cpu_count is not None else detect_cpu_count()
    ram = ram_bytes if ram_bytes is not None else detect_ram_bytes()
    perf = detect_performance_cpus() if performance_cpus is _UNSET else performance_cpus
    if perf is not None:
        perf = max(1, min(perf, cores))  # afinidade/cgroup podem limitar abaixo
    return {
        "machine_id": machine_id if machine_id is not None else detect_machine_id(),
        "hostname": host,
        "cpu_count": cores,
        "performance_cpus": perf,
        "hybrid": perf is not None,
        "ram_bytes": ram,
        "ram_gib": round(ram / _GIB, 1) if ram else None,
        "platform": platform.system(),
    }
