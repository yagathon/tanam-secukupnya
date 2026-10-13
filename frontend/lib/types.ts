// Shapes returned by the FastAPI backend (see backend/app/service.py).

export type Channel = "B2B" | "B2C";

export interface Zone {
  name: string;
  bed_day_from: number;
  bed_day_to: number;
  kg_factor: number;
  grade_share: Record<"A" | "B" | "C", number>;
  fits: Channel[];
}

export interface DemandLine {
  id: string;
  channels: Channel[];
  target_zone: string;
}

export interface Crop {
  id: string;
  name: string;
  nursery_days: number;
  zones: Zone[];
  demand_lines: DemandLine[];
}

export interface Farmer {
  id: string;
  alias: string;
  beds: Record<string, number>;
}

export interface Partner {
  id: string;
  alias: string;
  segment: string;
  corridor: Record<string, { min_kg: number; max_kg: number }>; // key "crop/line"
}

export interface Household {
  id: string;
  alias: string;
  basket: Record<string, number>;
  shortfall_weeks: string[];
}

export interface Batch {
  id: string;
  crop: string;
  line: string;
  farmer_id: string;
  beds: number;
  seeded_on: string;
  transplanted_on: string;
  status: string;
  note?: string;
}

export interface SignalDoc {
  id: string;
  scope: string;
  effect_pct: number;
  week_from: string;
  week_to: string;
  source: "note" | "calendar";
  cause: string;
  crop?: string | null;
  accepted?: boolean;
  status?: "accepted" | "rejected";
  cause_category?: string;
  open_ended?: boolean;
  note_id?: string;
}

export interface HarvestIssue {
  farmer_id: string;
  crop: string;
  loss_pct: number;
  delay_days: number;
  harvest_week: string | null;
  cause: string;
  cause_category: string;
}

export interface NoteDoc {
  id: string;
  text: string;
  sender: string;
  received_on: string;
  kind: "signals" | "harvest_issue" | "none";
  summary_en: string;
  harvest_issue: HarvestIssue | null;
  status: "proposed" | "no_action" | "accepted" | "rejected";
  accepted?: boolean;
  dropped: string[];
  model: string;
  cached: boolean;
  signals?: SignalDoc[];
}

export interface State {
  today: string;
  synthetic: boolean;
  crops: Crop[];
  farmers: Farmer[];
  partners: Partner[];
  households: Household[];
  batches: Batch[];
  signals: SignalDoc[];
  notes: NoteDoc[];
}

export interface ForecastPoint {
  week: string;
  expected: number;
  low: number;
  high: number;
  reasons: string[];
}

export interface SeriesView {
  series: { crop: string; line: string; channel: Channel; partner_id: string | null };
  key: string;
  history: { week: string; kg: number }[];
  forecast: ForecastPoint[];
}

export interface FarmerShare {
  farmer_id: string;
  beds: number;
  expected_kg: number;
  guaranteed_kg: number;
}

export interface NewBatch {
  seed_by: string;
  transplant_on: string;
  harvest_on: string;
  beds: number;
  expected_kg: number;
  farmers: FarmerShare[];
  top_up_kg: number;
}

export type PlanStatus = "covered" | "sow" | "surplus" | "bridge" | "shortfall";

export interface PlanWeek {
  week: string;
  target_kg: number;
  target_low_kg: number;
  in_ground_kg: number;
  net_kg: number;
  frozen: boolean;
  status: PlanStatus;
  bridge_kg: number;
  new_batch: NewBatch | null;
  notes: string[];
}

export interface Plan {
  crop: string;
  line: string;
  weeks: PlanWeek[];
  recovery_week: string | null;
  borrow_interest: number | null;
  warnings: string[];
}

export interface Served {
  customer_id: string;
  line: string;
  ordered_kg: number;
  served_kg: number;
}

export interface Scenario {
  crop: string;
  week: string;
  partners: Served[];
  households: Served[];
  cross_fills: { from_line: string; to_line: string; channel: Channel; kg: number; reason: string }[];
  surplus_kg: number;
  waste_kg: number;
  harvest_pct: number;
  harvested_kg: number;
  served_pct: number;
  preference_miss_kg: number;
  shorted_households: string[];
}

/** Everything the page loads once and hands to the tabs. */
export interface Data {
  state: State;
  series: SeriesView[];
  plans: Plan[];
}
