"""Demand forecast per series (crop × line × channel, B2B per partner): baseline + band + signals.

Deliberately simple and explainable: we have weeks, not years, of history.
- Baseline: exponentially weighted average of the history, after dividing out the effect of
  signals that are known to have applied in the past (so a Lebaran dip doesn't drag the level).
- Band: σ of the one-step-ahead residuals; low/high = expected ∓ z·σ·√h, widening with horizon h.
- Signals multiply expected (and the band) for the weeks and scopes they match. Calendar signals
  are capped at ±30%; an operator/farmer note overrides calendar signals of the same scope.
Every forecast number carries the list of reasons that shaped it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

CALENDAR_CAP = 0.30


@dataclass(frozen=True)
class Signal:
    id: str
    scope: str  # "all" | "channel:B2B" | "channel:B2C" | "partner:<id>"
    effect_pct: float  # +15 = 15% more demand
    week_from: date
    week_to: date  # inclusive (any week overlapping [from, to] is affected)
    source: str  # "note" | "calendar"
    cause: str
    crop: str | None = None  # None = every crop

    def factor(self) -> float:
        pct = self.effect_pct / 100
        if self.source == "calendar":
            pct = max(-CALENDAR_CAP, min(CALENDAR_CAP, pct))
        return max(0.0, 1 + pct)


@dataclass(frozen=True)
class Series:
    crop: str
    line: str
    channel: str  # "B2B" | "B2C"
    partner_id: str | None = None  # B2B is forecast per partner; B2C is pooled

    def scopes(self) -> set[str]:
        s = {"all", f"channel:{self.channel}"}
        if self.partner_id:
            s.add(f"partner:{self.partner_id}")
        return s


@dataclass
class ForecastPoint:
    week: date
    expected: float
    low: float
    high: float
    reasons: list[str] = field(default_factory=list)


def week_overlaps(week: date, sig: Signal) -> bool:
    return week <= sig.week_to and week + timedelta(days=6) >= sig.week_from


def active_signals(series: Series, week: date, signals: list[Signal]) -> list[Signal]:
    """Signals that apply to this series in this week, with notes overriding calendar per scope."""
    scopes = series.scopes()
    hits = [s for s in signals
            if s.scope in scopes and (s.crop is None or s.crop == series.crop) and week_overlaps(week, s)]
    noted = {s.scope for s in hits if s.source == "note"}
    return [s for s in hits if s.source == "note" or s.scope not in noted]


def combined_factor(sigs: list[Signal]) -> float:
    return math.prod((s.factor() for s in sigs), start=1.0)


def baseline(history: list[tuple[date, float]], series: Series, signals: list[Signal],
             alpha: float = 0.3) -> tuple[float, float]:
    """(level, σ of one-step-ahead residuals) from the signal-adjusted history."""
    if not history:
        return 0.0, 0.0
    adjusted = []
    for week, kg in sorted(history):
        f = combined_factor(active_signals(series, week, signals))
        adjusted.append(kg / f if f > 0 else kg)
    level = adjusted[0]
    residuals = []
    for x in adjusted[1:]:
        residuals.append(x - level)
        level = alpha * x + (1 - alpha) * level
    if len(residuals) > 1:
        mean = sum(residuals) / len(residuals)
        sigma = math.sqrt(sum((r - mean) ** 2 for r in residuals) / (len(residuals) - 1))
    else:
        sigma = 0.0
    return level, sigma


def forecast(history: list[tuple[date, float]], series: Series, start_week: date, horizon: int,
             signals: list[Signal] = (), alpha: float = 0.3, z: float = 1.28) -> list[ForecastPoint]:
    """Forecast `horizon` weeks from `start_week` (h = 1 for start_week). z=1.28 → ~80% band."""
    signals = list(signals)
    level, sigma = baseline(history, series, signals, alpha)
    points = []
    for h in range(1, horizon + 1):
        week = start_week + timedelta(weeks=h - 1)
        sigs = active_signals(series, week, signals)
        f = combined_factor(sigs)
        expected = level * f
        half = z * sigma * math.sqrt(h) * f
        reasons = [f"baseline {level:.1f} kg/week (weighted recent average)"]
        reasons += [f"{s.effect_pct:+g}%{' (capped)' if s.factor() != 1 + s.effect_pct / 100 else ''}"
                    f" {s.cause} [{s.source}]" for s in sigs]
        points.append(ForecastPoint(week, round(expected, 2), round(max(0.0, expected - half), 2),
                                    round(expected + half, 2), reasons))
    return points
