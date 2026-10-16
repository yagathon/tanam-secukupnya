// Shapes of the API on feat/daily-engine. backend/tests/test_api_contract.py pins the same keys.

export type LineId = "regular" | "baby" | (string & {});
export type NoteKind = "orders" | "harvest" | "sowing" | "loss" | "signal" | "none";

export interface CropLine { id: LineId; min_g: number; max_g: number; channels: string[] }
export interface Crop {
  id: string; name: string; nursery_days: number; growth_curve: [number, number][]; spread_ratio: number;
  germination: number; survival: number; seeds_per_gram: number; grams_per_teaspoon: number; max_bed_day: number;
  max_seedlings_per_sowing: number; sow_weekdays: number[]; lines: CropLine[];
}
export interface Buyer {
  id: string; alias: string; segment: string; weekdays: number[];
  lines: Record<string, { kg: number; min_kg: number }>;
}
export interface Household { id: string; alias: string; line: LineId; kg: number; weekdays: number[] }
export interface Sender { id: string; alias: string }
export interface State {
  today: string; synthetic: boolean; crop: Crop; buyers: Buyer[]; households: Household[]; senders: Sender[];
  reference?: Reference; sandbox?: boolean;
}

export interface Signal {
  scope: string; line: LineId | null; effect_pct: number; date_from: string; date_to: string;
  open_ended?: boolean; cause: string; cause_category?: string;
}
export interface Proposal {
  kind: NoteKind; summary_en: string;
  orders: { buyer: string; line: LineId; kg: number; day: string }[];
  harvest: { bed: string; batch: string; kg: number; big5_g: number | null; small5_g: number | null } | null;
  sowing: { line: LineId; postponed: boolean; seedlings: number | null; reason: string } | null;
  loss: { bed: string; batch: string; pct: number; cause: string; cause_category: string } | null;
  signals: Signal[];
}
export interface NoteDoc {
  id: string; text: string; sender: string; received_on: string; proposal: Proposal; kind: NoteKind;
  summary_en: string; status: "proposed" | "no_action" | "accepted" | "rejected"; dropped: string[];
  model: string; cached: boolean; events?: unknown[]; preview?: string[];
  preview_events?: Record<string, unknown>[];
}

export interface SowSummary {
  day: string; weekday: string; seedlings: number; seeds_g: number; teaspoons: number; shortfall_ahead_kg: number;
}
export interface TodayLine {
  line: LineId; need_kg: number; ceiling_kg: number; send_kg: number; short_kg: number; rotated: string[];
  sow: SowSummary;
}
export interface Today { today: string; weekday: string; lines: TodayLine[]; pending: NoteDoc[]; seq: number }

export interface BatchRow {
  id: string; label: string; sown_on: string; bed_day: number; stage: "nursery" | "bed"; seedlings: number;
  plants_left: number; avg_g: number | null; size_pct: number; spread: number; sampled: boolean;
  ready_from: string; until: string; available_tomorrow_kg: number; waste_plants: number;
}
export interface ChartDay { day: string; available_kg: number; need_kg: number; short_kg: number }
export interface BedsLine { line: LineId; min_g: number; max_g: number; batches: BatchRow[]; chart: ChartDay[] }
export interface Beds { today: string; lines: BedsLine[] }

export interface DayKg { day: string; kg: number }
export interface TomorrowLine {
  line: LineId; day: string; need_kg: number; available_kg: number; ceiling_kg: number; send_kg: number;
  short_kg: number;
  buyers: { id: string; alias: string; known: boolean; ordered_kg: number; served_kg: number; min_kg: number }[];
  households: { id: string; alias: string; ordered_kg: number; served_kg: number }[];
  borrowing: DayKg[];
}
export interface Tomorrow { today: string; lines: TomorrowLine[] }

export interface SowLine {
  line: LineId; day: string; seedlings: number; seeds_g: number; teaspoons: number; ready_from: string;
  covers_until: string; gap_kg: number; capped: boolean; shortfall_ahead: DayKg[]; missed: string[];
  postponed: { day: string; reason: string }[];
  basis: { need: string; survival: number; germination: number; seeds_per_gram: number; grams_per_teaspoon: number;
    max_seedlings: number };
}
export interface Sow { today: string; lines: SowLine[] }

export interface DemandDay { day: string; low: number; expected: number; high: number; protected: number; target: number }
export interface Demand {
  today: string;
  market: { factor: number; buyers: number; text: string };
  series: { key: string; label: string; line: LineId; usual_kg: number; level_kg: number; shape: number[] }[];
  signals: (Signal & { t?: string })[];
  lines: { line: LineId; days: DemandDay[] }[];
}

export type Strategy = "cobweb" | "fixed" | "tanam";
export interface SeasonMetrics { waste_pct: number; b2b_fill_pct: number; hh_fill_pct: number; sowing_cv: number }
export interface Season {
  days: number; seeds: number[]; main_seed: number; synthetic: boolean;
  summary: Record<Strategy, SeasonMetrics>;
  runs: (SeasonMetrics & { strategy: Strategy; seed: number })[];
  sowings: Record<Strategy, { line: LineId; day: string; seedlings: number }[]>;
}

/** Everything the tabs need, refetched after every change (Season is loaded by its own tab). */
export interface Data { state: State; today: Today; beds: Beds; tomorrow: Tomorrow; sow: Sow; demand: Demand }

export interface SetupLine { id: string; min_g: number; max_g: number }
export interface SetupCrop {
  name: string; nursery_days: number; growth_curve: [number, number][]; spread_ratio: number;
  germination: number; survival: number; seeds_per_gram: number; grams_per_teaspoon: number;
  max_bed_day: number; max_seedlings_per_sowing: number; sow_weekdays: number[]; lines: SetupLine[];
}
export interface SetupBuyer {
  id?: string; name: string; type: "business" | "household"; line: string;
  usual_kg_per_week: number; weekdays: number[]; min_kg: number;
}
export interface SetupBed { line: string; sown_on: string; seedlings: number }
export interface Setup { start: string; learn_reference: boolean; crop: SetupCrop; buyers: SetupBuyer[]; beds: SetupBed[] }
export interface SetupDoc { saved: boolean; setup: Setup; locked_start: boolean }
export interface Reference { start: [number, number][]; now: [number, number][]; samples: number[] }
export interface TrailLine {
  low: number; high: number; ready: number; ceiling: number; send: number;
  short: number | null; sow_day: string | null; sow_seedlings: number;
}
export interface TrailRow { day: string; live: boolean; lines: Record<string, TrailLine>; inputs: string[]; ref: string[] }
