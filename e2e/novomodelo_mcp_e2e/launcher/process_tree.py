"""Encerra um processo e TODOS os descendentes, inclusive os que escapam de ``taskkill /T``.

``taskkill /T`` percorre a árvore num instante: um filho criado logo depois do
instantâneo vira órfão e segue vivo (no motor de carga, um servidor MCP sobrando
com CPU e memória). No Windows o processo entra num Job Object com
``KILL_ON_JOB_CLOSE``: o job inclui todo descendente criado depois, órfão ou não,
e fecha junto com o launcher. Em POSIX o processo é líder de sessão e o grupo
inteiro recebe SIGKILL.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

__all__ = ["ProcessTree"]

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _create_kill_on_close_job():  # pragma: no cover - só no Windows
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        kernel32.CloseHandle(job)
        return None
    return kernel32, job


class ProcessTree:
    """Árvore de um ``Popen`` recém-criado: ``attach`` logo após o spawn, ``kill`` para encerrar."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._job = None
        if sys.platform == "win32":
            self._job = self._attach_job(process)

    @staticmethod
    def _attach_job(process: subprocess.Popen):  # pragma: no cover - só no Windows
        created = _create_kill_on_close_job()
        if created is None:
            return None
        kernel32, job = created
        handle = process._handle  # ty: ignore[unresolved-attribute] - privado, fora do typeshed
        if not kernel32.AssignProcessToJobObject(job, int(handle)):
            kernel32.CloseHandle(job)
            return None
        return kernel32, job

    def kill(self) -> None:
        """SIGKILL no grupo (POSIX) ou termina o job e, por garantia, roda ``taskkill /T``."""
        process = self._process
        if sys.platform != "win32":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return
        if self._job is not None:
            kernel32, job = self._job
            kernel32.TerminateJobObject(job, 1)
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )

    def close(self) -> None:
        """Fecha o handle do job (com ``KILL_ON_JOB_CLOSE``, mata o que ainda restar nele)."""
        if self._job is not None:
            kernel32, job = self._job
            kernel32.CloseHandle(job)
            self._job = None
