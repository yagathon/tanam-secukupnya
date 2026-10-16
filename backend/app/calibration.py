"""Slow learning of the reference growth curve from harvest samples (model B, layer 2).

A bed's own size factor absorbs its stunting; the reference only moves when many healthy beds at
the same age disagree with it. Each node keeps the last few ratios (sample avg ÷ reference) it was
near, and moves by a capped fraction of their median — so one odd bed cannot bend the curve.
"""

from __future__ import annotations

import statistics

Pts = tuple[tuple[float, float], ...]
Kept = tuple[tuple[float, ...], ...]


def node_weights(xs: list[float], t: float) -> list[float]:
    """Linear weights of the two nodes around bed day t; outside the curve the end node gets 1."""
    w = [0.0] * len(xs)
    if t <= xs[0]:
        w[0] = 1.0
    elif t >= xs[-1]:
        w[-1] = 1.0
    else:
        i = next(i for i in range(len(xs) - 1) if xs[i] <= t <= xs[i + 1])
        w1 = (t - xs[i]) / (xs[i + 1] - xs[i])
        w[i], w[i + 1] = 1 - w1, w1
    return w


def update(pts: Pts, kept: Kept, t: float, ratio: float, keep: int = 5, gain: float = 0.3,
           cap: float = 0.05) -> tuple[Pts, Kept]:
    kept = kept or tuple(() for _ in pts)
    ws = node_weights([x for x, _ in pts], t)
    new_pts, new_kept = [], []
    for (x, y), k, w in zip(pts, kept, ws):
        if w > 0:
            k = (k + (ratio,))[-keep:]
            step = max(-cap, min(cap, gain * (statistics.median(k) - 1) * w))
            y = y * (1 + step)
        new_pts.append((x, y))
        new_kept.append(k)
    for i in range(1, len(new_pts)):                       # strictly increasing, by ≥ 1 g
        x, y = new_pts[i]
        if y < new_pts[i - 1][1] + 1:
            new_pts[i] = (x, new_pts[i - 1][1] + 1)
    return tuple(new_pts), tuple(new_kept)
