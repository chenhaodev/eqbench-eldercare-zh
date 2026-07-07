"""Wilson 95% 置信区间（率指标用，纯 stdlib，无 scipy/numpy）。

来源: med-agent-os-api/eval/wilson.py，逐字复用。任何「hits/n」型率指标都该用它
报 CI，而不是只报点估计——点估计在小 n 下极不稳（见 SKILL.md「统计+诚实纪律」）。
"""
from __future__ import annotations

import math


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """返回 (p, lo, hi)。n=0 → (0,0,0)。z=1.96 → 95%。"""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = hits / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return round(p, 4), round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)


if __name__ == "__main__":
    # 自检：18/30 成功 → 点估计 0.6, 95% CI [0.423, 0.754]（与源仓库一致）
    print("wilson(18,30) =", wilson(18, 30))
    print("wilson(0,0)   =", wilson(0, 0))
    print("wilson(50,50) =", wilson(50, 50))
