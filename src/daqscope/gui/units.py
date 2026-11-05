from __future__ import annotations

import math
from typing import List

_PREFIX = {-12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M"}


def steps_125(lo: float, hi: float) -> List[float]:
    """1-2-5 sequence values within [lo, hi]."""
    out = []
    k = math.floor(math.log10(lo)) - 1
    while 10.0 ** k <= hi * 10:
        for m in (1, 2, 5):
            v = round(m * 10.0 ** k, 12)
            if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9):
                out.append(v)
        k += 1
    return out


def ceil_125(x: float) -> float:
    """Smallest 1-2-5 value that is at least x."""
    k = math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        v = m * 10.0 ** k
        if v >= x * (1 - 1e-9):
            return round(v, 12)
    return 10.0 ** (k + 1)


def eng(value: float, unit: str = "", digits: int = 3) -> str:
    """Engineering notation with an SI prefix, e.g. 0.0025 V -> '2.50 mV'."""
    if value != value:
        return "--"
    if value == 0:
        return f"0 {unit}".strip()
    exp = int(math.floor(math.log10(abs(value)) / 3) * 3)
    exp = max(-12, min(6, exp))
    mant = value / 10.0 ** exp
    dec = max(0, digits - 1 - int(math.floor(math.log10(abs(mant)))))
    return f"{mant:.{dec}f} {_PREFIX[exp]}{unit}".strip()
