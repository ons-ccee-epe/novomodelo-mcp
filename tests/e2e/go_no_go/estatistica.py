"""Estatística da bateria: intervalo de confiança de Wilson para uma proporção."""

from __future__ import annotations

from math import sqrt


def wilson(acertos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = acertos / n
    denominador = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denominador
    margem = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominador
    return (max(0.0, centro - margem), min(1.0, centro + margem))
