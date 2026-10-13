"""Crop growth model: one engine for fast and slow crops.

Everything crop-specific lives in data (a crop profile dict, see data/seed/crops.json).
Adding a crop means adding a profile, not code. Days are counted *in the bed*, i.e. after
transplant; the seedling (nursery) phase comes before that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GRADES = ("A", "B", "C")
CHANNELS = ("B2B", "B2C")


@dataclass(frozen=True)
class Zone:
    name: str
    bed_day_from: int
    bed_day_to: int  # inclusive
    kg_factor: float  # kg relative to the best zone (best = 1.0)
    grade_share: dict[str, float]  # A/B/C, sums to 1
    fits: frozenset[str]  # channels this size suits
    extra_pest_loss: float = 0.0  # added on top of the crop's baseline pest loss

    @property
    def midpoint(self) -> int:
        return (self.bed_day_from + self.bed_day_to) // 2

    def contains(self, bed_day: int) -> bool:
        return self.bed_day_from <= bed_day <= self.bed_day_to


@dataclass(frozen=True)
class DemandLine:
    """A separately planted batch type for one crop, e.g. pakcoy regular vs. baby."""

    id: str
    channels: frozenset[str]
    target_zone: str
    density_factor: float = 1.0  # plants per bed relative to the crop default
    grams_factor: float = 1.0  # grams per plant relative to the crop default at the best zone


@dataclass(frozen=True)
class Crop:
    id: str
    name: str
    nursery_days: int
    plants_per_bed: int
    grams_per_plant: float  # at the best zone
    pest_loss: float  # baseline share of plants lost
    zones: tuple[Zone, ...]
    demand_lines: tuple[DemandLine, ...] = field(default_factory=tuple)

    @property
    def kg_per_bed(self) -> float:
        """Best-zone kg from one successful bed, before pest loss."""
        return self.plants_per_bed * self.grams_per_plant / 1000

    def zone(self, name: str) -> Zone:
        for z in self.zones:
            if z.name == name:
                return z
        raise KeyError(f"{self.id}: no zone {name!r}")

    def zone_at(self, bed_day: int) -> Zone | None:
        """The zone a batch is in on this bed day; None = not harvestable (too early or waste)."""
        for z in self.zones:
            if z.contains(bed_day):
                return z
        return None

    def line(self, line_id: str) -> DemandLine:
        for ln in self.demand_lines:
            if ln.id == line_id:
                return ln
        raise KeyError(f"{self.id}: no demand line {line_id!r}")

    @property
    def last_bed_day(self) -> int:
        return max(z.bed_day_to for z in self.zones)

    def pest_loss_at(self, bed_day: int) -> float:
        z = self.zone_at(bed_day)
        return min(1.0, self.pest_loss + (z.extra_pest_loss if z else 0.0))

    def harvest_kg(self, beds: float, bed_day: int, line_id: str | None = None,
                   loss_pct: float = 0.0) -> float:
        """Expected kg harvested from `beds` on `bed_day` (0 outside every zone).

        `loss_pct` is batch-specific damage already observed (e.g. from a farmer's note);
        the crop's pest loss for that zone is applied on top as the remaining risk.
        """
        z = self.zone_at(bed_day)
        if z is None:
            return 0.0
        ln = self.line(line_id) if line_id else None
        density = ln.density_factor if ln else 1.0
        grams = ln.grams_factor if ln else 1.0
        kg = beds * self.kg_per_bed * density * grams * z.kg_factor
        return kg * (1 - loss_pct) * (1 - self.pest_loss_at(bed_day))

    def kg_per_bed_for_line(self, line_id: str) -> float:
        """Expected kg per bed at the line's target-zone midpoint, after baseline pest loss."""
        ln = self.line(line_id)
        return self.harvest_kg(1, self.zone(ln.target_zone).midpoint, line_id)

    def days_to_harvest(self, line_id: str) -> int:
        """Seed → target-zone midpoint, in days: the lead time sowing cannot beat."""
        ln = self.line(line_id)
        return self.nursery_days + self.zone(ln.target_zone).midpoint


def crop_from_dict(d: dict) -> Crop:
    zones = tuple(
        Zone(
            name=z["name"],
            bed_day_from=z["bed_day_from"],
            bed_day_to=z["bed_day_to"],
            kg_factor=z["kg_factor"],
            grade_share=dict(z["grade_share"]),
            fits=frozenset(z["fits"]),
            extra_pest_loss=z.get("extra_pest_loss", 0.0),
        )
        for z in d["zones"]
    )
    lines = tuple(
        DemandLine(
            id=ln["id"],
            channels=frozenset(ln["channels"]),
            target_zone=ln["target_zone"],
            density_factor=ln.get("density_factor", 1.0),
            grams_factor=ln.get("grams_factor", 1.0),
        )
        for ln in d.get("demand_lines", [])
    )
    crop = Crop(
        id=d["id"],
        name=d["name"],
        nursery_days=d["nursery_days"],
        plants_per_bed=d["plants_per_bed"],
        grams_per_plant=d["grams_per_plant"],
        pest_loss=d["pest_loss"],
        zones=zones,
        demand_lines=lines,
    )
    validate(crop)
    return crop


def validate(crop: Crop) -> None:
    ordered = sorted(crop.zones, key=lambda z: z.bed_day_from)
    for a, b in zip(ordered, ordered[1:]):
        if b.bed_day_from <= a.bed_day_to:
            raise ValueError(f"{crop.id}: zones {a.name} and {b.name} overlap")
    for z in crop.zones:
        if z.bed_day_from > z.bed_day_to:
            raise ValueError(f"{crop.id}: zone {z.name} ends before it starts")
        if set(z.grade_share) != set(GRADES) or abs(sum(z.grade_share.values()) - 1) > 1e-9:
            raise ValueError(f"{crop.id}: zone {z.name} grade shares must cover A/B/C and sum to 1")
        if not z.fits <= set(CHANNELS):
            raise ValueError(f"{crop.id}: zone {z.name} has unknown channels {z.fits}")
    for ln in crop.demand_lines:
        crop.zone(ln.target_zone)  # raises if missing
        if not ln.channels <= set(CHANNELS):
            raise ValueError(f"{crop.id}: line {ln.id} has unknown channels {ln.channels}")
