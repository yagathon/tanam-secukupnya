"""Daily demand: expected(series, d) = shape[weekday] × level × season × market × signal factors.

Series: one per B2B buyer × line ("b2b:<buyer>:<line>") plus one pooled households series per
line ("hh:<line>"). The weekday shape is fixed from history (D7). A level changes only on confirmed
evidence: each finished week (Mon–Sun) is judged on its total, actual ÷ forecast, as above (> +10%),
below (< −10%) or normal; three weeks in a row on the same side move the level by their mean ratio.
A few high days or one big order never move it. Actuals are divided by the market factor, so a
market-wide drop is carried by `market` alone, never twice.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

ALPHA = 0.2                      # only widens the band with the horizon now; levels move by weeks
WEEK_BAND, CONFIRM = 0.10, 3     # a week counts above/below past ±10%; 3 in a row move the level
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
    streak: tuple[str, int] = ("", 0)  # ("above" | "below" | "", finished weeks in a row on that side)


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


def season_factor(season: dict | None, d: date) -> float:
    """The setup's farm-wide season for day d: month block (1–7, 8–14, 15–21, 22–end; % of a month,
    25 each = flat) × year index for the month (100 = normal). None (the demo world) = 1."""
    if not season:
        return 1.0
    block = min((d.day - 1) // 7, 3)
    return season["month_pct"][block] / 25 * season["year_index"][d.month - 1] / 100


def _block(d: date) -> int:
    return min((d.day - 1) // 7, 3)


@dataclass
class DemandModel:
    fits: dict[str, Fit]
    market: float
    market_buyers: int
    season: dict | None = None             # the effective season: setup's, with any confirmed month blocks
    learned_blocks: list[int] = field(default_factory=list)   # month blocks moved away from the setup


def fit(history: dict[str, dict[date, float]], shape_until: date, today: date,
        priors: dict[str, list[float]] | None = None, season: dict | None = None) -> DemandModel:
    """Walk every day before `today` in order: market factor from the B2B ratios of the previous 7
    days, then each series' level update. `shape_until`: shape and baseline are fitted only on days
    before it and then stay fixed, so a market move shows up as m instead of seeping into levels.
    `priors`: series → setup estimate (kg Mon..Sun); such a series starts from the estimate instead of
    from history, with a wide σ until it has its own residuals. `season`: see season_factor; it is
    divided out of every actual, so a December peak the setup predicted doesn't lift the level. Its month
    blocks are checked at each month's end, farm-wide, on their share of the month (months covered from
    day 1 only): a block 3 months in a row more than 10% off moves to the mean share it showed."""
    priors = priors or {}
    season = {"month_pct": list(season["month_pct"]), "year_index": list(season["year_index"])} if season else None
    history = {k: history.get(k, {}) for k in list(history) + [k for k in priors if k not in history]}
    days = sorted({d for s in history.values() for d in s if d < today})
    shapes = {k: shape_of({d: v for d, v in s.items() if d < shape_until}) for k, s in history.items()}
    fits: dict[str, Fit] = {}
    resid: dict[str, list[float]] = {k: [] for k in history}
    levels_hist: dict[str, list[tuple[date, float]]] = {k: [] for k in history}
    ratio_log: list[tuple[date, str, float]] = []  # (day, buyer, actual ÷ (shape × level))
    month: list = [None, [0.0] * 4, [0.0] * 4]   # [first of month, actual kg per block, forecast without the month pattern]
    mstreak: list[list] = [[] for _ in range(4)]  # per block: ("above" | "below", observed share) of the current streak
    learned: set[int] = set()

    def close_month(first: date) -> None:
        """Judge a finished month's block shares farm-wide; a block 3 months in a row on one side moves."""
        _, a, fc = month
        month[:] = [None, [0.0] * 4, [0.0] * 4]
        if not season or not days or days[0] > first or any(x <= 0 for x in fc):
            return
        r = [x / y for x, y in zip(a, fc)]
        if sum(r) <= 0:                                  # a month with no orders has no shape to judge
            return
        obs = [100 * x / sum(r) for x in r]
        pct = season["month_pct"]
        for b in range(4):
            side = "above" if obs[b] > pct[b] * (1 + WEEK_BAND) else "below" if obs[b] < pct[b] * (1 - WEEK_BAND) else ""
            if not side or (mstreak[b] and mstreak[b][-1][0] != side):
                mstreak[b] = []
            if side:
                mstreak[b].append((side, obs[b]))
        moved = [b for b in range(4) if len(mstreak[b]) >= CONFIRM]
        for b in moved:
            pct[b] = statistics.fmean(o for _, o in mstreak[b])
            mstreak[b] = []
            learned.add(b)
        if moved:
            tot = sum(pct)
            season["month_pct"] = [x * 100 / tot for x in pct]

    week: dict[str, list] = {k: [None, 0.0, 0.0] for k in history}   # [Monday, actual sum, weekday-shape sum]
    implied: dict[str, list[float]] = {k: [] for k in history}        # the week levels of the current streak

    def close_week(k: str, on: date) -> None:
        """Judge series k's finished week on its total; on 3 in a row, move the level (`on` = the day after).
        The week's own level (its actual ÷ its weekday shape) against the level: >10% off is a side. A week
        begun before the first day of history is not judged, like a month not covered from day 1."""
        mon, a, sh = week[k]
        week[k] = [None, 0.0, 0.0]
        if mon is None or sh <= 0 or mon < days[0]:
            return
        f, lw = fits[k], a / sh
        if f.level > 0:
            q = lw / f.level
            side = "above" if q > 1 + WEEK_BAND else "below" if q < 1 - WEEK_BAND else ""
        else:                                          # a level confirmed down to 0 can still come back
            side = "above" if lw > 0 else ""
        if not side:
            f.streak, implied[k] = ("", 0), []
            return
        if f.streak[0] != side:
            implied[k] = []
        implied[k].append(lw)
        f.streak = (side, len(implied[k]))
        if len(implied[k]) >= CONFIRM:
            f.level = statistics.fmean(implied[k])      # = level × the mean of the weeks' ratios
            f.streak, implied[k] = ("", 0), []
            levels_hist[k].append((on, f.level))
    m, nb = 1.0, 0
    for k, s in history.items():
        if k in priors:
            fits[k] = prior_fit(k, priors[k])
            levels_hist[k].append((date.min, fits[k].level))
            continue
        sh = shapes[k]
        init = [v / (sh[d.weekday()] * season_factor(season, d)) for d, v in s.items() if days and d < days[0] + timedelta(days=INIT_DAYS) and sh[d.weekday()] > 0]
        base = [v / (sh[d.weekday()] * season_factor(season, d)) for d, v in s.items() if d < shape_until and sh[d.weekday()] > 0]
        lv = statistics.fmean(init) if init else 0.0
        fits[k] = Fit(k, sh, lv, 0.0, lv, statistics.fmean(base) if base else lv)
        levels_hist[k].append((date.min, lv))
    for d in days:
        first = d.replace(day=1)
        if month[0] is not None and month[0] != first:
            close_month(month[0])
        month[0] = first
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
            actual = s[d] / season_factor(season, d)
            if k in priors and f.baseline <= 0:          # no estimate given: the first order sets the level
                if actual <= 0:
                    continue
                f.level = f.baseline = f.usual = actual / (sh * m)
                f.sigma = PRIOR_SIGMA * f.level
                levels_hist[k].append((d, f.level))
                continue
            if k.startswith("b2b:"):
                ratio_log.append((d, k.split(":")[1], actual / (sh * f.baseline)))
            mon = d - timedelta(days=d.weekday())
            if week[k][0] is not None and week[k][0] != mon:
                close_week(k, d)
            week[k][0] = mon
            week[k][1] += actual / m
            week[k][2] += sh
            month[1][_block(d)] += s[d]
            month[2][_block(d)] += sh * f.level * m * (season["year_index"][d.month - 1] / 100 if season else 1.0)
            r = actual / (sh * m) - f.level
            rs = resid[k]
            rs.append(r)
            wide = PRIOR_SIGMA if k in priors else 0.15
            f.sigma = _sd(rs[-28:]) if len(rs) >= 5 else abs(f.level) * wide
    if month[0] is not None and (month[0] + timedelta(days=32)).replace(day=1) <= today:
        close_month(month[0])                           # the last month counts once it has fully passed
    for k in history:                                   # the last week counts once it has fully passed
        if week[k][0] is not None and week[k][0] + timedelta(days=7) <= today:
            close_week(k, week[k][0] + timedelta(days=7))
    for k, f in fits.items():
        old = [lv for d, lv in levels_hist[k] if d <= today - timedelta(days=14)]
        f.usual = old[-1] if old else f.level
    return DemandModel(fits, m, nb, season, sorted(learned))


def expected(model: DemandModel, key: str, d: date, factor: float = 1.0) -> float:
    f = model.fits[key]
    return f.shape[d.weekday()] * f.level * model.market * season_factor(model.season, d) * factor


def band(model: DemandModel, key: str, d: date, h: int, factor: float = 1.0) -> tuple[float, float, float]:
    """(low, expected, high) for a day h ≥ 1 days ahead."""
    f = model.fits[key]
    e = expected(model, key, d, factor)
    w = Z80 * f.sigma * math.sqrt(1 + (max(h, 1) - 1) * ALPHA ** 2) * f.shape[d.weekday()] * model.market * season_factor(model.season, d) * factor
    return max(0.0, e - w), e, e + w
