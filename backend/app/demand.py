"""Daily demand: expected(series, d) = shape[weekday] × level × market × signal factors.

Series: one per B2B buyer × line ("b2b:<buyer>:<line>") plus one pooled households series per
line ("hh:<line>"). The weekday shape is fixed from history (D7). Each series' level is smoothed
from actual ÷ (shape × market), so a market-wide drop is carried by `market` alone, never twice.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

ALPHA, ALPHA_SHIFT = 0.2, 0.6
Z80 = 1.28
MARKET_WINDOW, MARKET_MIN_BUYERS, MARKET_AGREE, MARKET_MIN_MOVE = 7, 3, 0.6, 0.05
INIT_DAYS = 14
PRIOR_SIGMA = 0.5


@dataclass
class Fit:
    key: str
    shape: list[float]               # Mon..Sun, mean 1 over order days
    level: float                     # kg on an average order day, market divided out
    sigma: float                     # σ of one-step residuals, in level units
    usual: float                     # level 14 days ago (for "usual 6.0 → now 4.2")
    baseline: float                  # mean of actual ÷ shape over the shape period (the market check's yardstick)


def _sd(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def shape_of(history: dict[date, float]) -> list[float]:
    """Mean by weekday ÷ overall mean; a weekday with no demand gets 0."""
    by = [[] for _ in range(7)]
    for d, v in history.items():
        by[d.weekday()].append(v)
    means = [statistics.fmean(x) if x else 0.0 for x in by]
    pos = [m for m in means if m > 0]
    overall = statistics.fmean(pos) if pos else 0.0
    return [round(m / overall, 4) if overall else 0.0 for m in means]


def market_factor(ratios: dict[str, list[float]]) -> tuple[float, int]:
    """ratios: buyer → their actual ÷ (shape × level) over the last 7 days. Returns (m, buyers)."""
    per = [statistics.fmean(v) for v in ratios.values() if v]
    if len(per) < MARKET_MIN_BUYERS:
        return 1.0, len(per)
    m = statistics.median(per)
    side = sum(1 for r in per if (r < 1) == (m < 1) and r != 1) / len(per)
    if side < MARKET_AGREE or abs(m - 1) < MARKET_MIN_MOVE:
        return 1.0, len(per)
    return round(m, 3), len(per)


def prior_fit(key: str, week: list[float]) -> Fit:
    """A setup estimate (kg per weekday) as a starting fit: shape from the weekdays, σ = 50% of level."""
    pos = [v for v in week if v > 0]
    if not pos:
        return Fit(key, [1.0] * 7, 0.0, 0.0, 0.0, 0.0)
    lv = statistics.fmean(pos)
    return Fit(key, [round(v / lv, 4) for v in week], lv, PRIOR_SIGMA * lv, lv, lv)


@dataclass
class DemandModel:
    fits: dict[str, Fit]
    market: float
    market_buyers: int


def fit(history: dict[str, dict[date, float]], shape_until: date, today: date,
        priors: dict[str, list[float]] | None = None) -> DemandModel:
    """Walk every day before `today` in order: market factor from the B2B ratios of the previous 7
    days, then each series' level update. `shape_until`: shape and baseline are fitted only on days
    before it and then stay fixed, so a market move shows up as m instead of seeping into levels.
    `priors`: series → setup estimate (kg Mon..Sun); such a series starts from the estimate instead of
    from history, with a wide σ until it has its own residuals."""
    priors = priors or {}
    history = {k: history.get(k, {}) for k in list(history) + [k for k in priors if k not in history]}
    days = sorted({d for s in history.values() for d in s if d < today})
    shapes = {k: shape_of({d: v for d, v in s.items() if d < shape_until}) for k, s in history.items()}
    fits: dict[str, Fit] = {}
    resid: dict[str, list[float]] = {k: [] for k in history}
    levels_hist: dict[str, list[tuple[date, float]]] = {k: [] for k in history}
    ratio_log: list[tuple[date, str, float]] = []  # (day, buyer, actual ÷ (shape × level))
    m, nb = 1.0, 0
    for k, s in history.items():
        if k in priors:
            fits[k] = prior_fit(k, priors[k])
            continue
        sh = shapes[k]
        init = [v / sh[d.weekday()] for d, v in s.items() if days and d < days[0] + timedelta(days=INIT_DAYS) and sh[d.weekday()] > 0]
        base = [v / sh[d.weekday()] for d, v in s.items() if d < shape_until and sh[d.weekday()] > 0]
        lv = statistics.fmean(init) if init else 0.0
        fits[k] = Fit(k, sh, lv, 0.0, lv, statistics.fmean(base) if base else lv)
    for d in days:
        window = {}
        for (dd, buyer, q) in ratio_log:
            if d - timedelta(days=MARKET_WINDOW) <= dd < d:
                window.setdefault(buyer, []).append(q)
        m, nb = market_factor(window)
        for k, s in history.items():
            f = fits[k]
            sh = f.shape[d.weekday()]
            if sh <= 0 or d not in s or (f.baseline <= 0 and k not in priors):
                continue
            actual = s[d]
            if k in priors and f.baseline <= 0:          # no estimate given: the first order sets the level
                if actual <= 0:
                    continue
                f.level = f.baseline = f.usual = actual / (sh * m)
                f.sigma = PRIOR_SIGMA * f.level
                levels_hist[k].append((d, f.level))
                continue
            if k.startswith("b2b:"):
                ratio_log.append((d, k.split(":")[1], actual / (sh * f.baseline)))
            r = actual / (sh * m) - f.level
            rs = resid[k]
            wide = PRIOR_SIGMA if k in priors else 0.15
            sigma = _sd(rs[-28:]) if len(rs) >= 5 else abs(f.level) * wide
            last = rs[-2:] + [r]
            shift = len(last) == 3 and len({x > 0 for x in last}) == 1 and all(abs(x) > 0.5 * sigma for x in last)
            f.level = max(0.0, f.level + (ALPHA_SHIFT if shift else ALPHA) * r)
            rs.append(r)
            f.sigma = _sd(rs[-28:]) if len(rs) >= 5 else abs(f.level) * wide
            levels_hist[k].append((d, f.level))
    for k, f in fits.items():
        old = [lv for d, lv in levels_hist[k] if d <= today - timedelta(days=14)]
        f.usual = old[-1] if old else f.level
    return DemandModel(fits, m, nb)


def expected(model: DemandModel, key: str, d: date, factor: float = 1.0) -> float:
    f = model.fits[key]
    return f.shape[d.weekday()] * f.level * model.market * factor


def band(model: DemandModel, key: str, d: date, h: int, factor: float = 1.0) -> tuple[float, float, float]:
    """(low, expected, high) for a day h ≥ 1 days ahead."""
    f = model.fits[key]
    e = expected(model, key, d, factor)
    w = Z80 * f.sigma * math.sqrt(1 + (max(h, 1) - 1) * ALPHA ** 2) * f.shape[d.weekday()] * model.market * factor
    return max(0.0, e - w), e, e + w
