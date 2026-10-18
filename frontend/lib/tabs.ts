/** The tab order both pages share (the sandbox greys out the Simulation report: it needs the demo's known future). */
export const TAB_ORDER = ["setup", "today", "beds", "tomorrow", "sow", "demand", "impact", "report", "trail"] as const;
export const TAB_LABEL: Record<(typeof TAB_ORDER)[number], string> = {
  setup: "Setup", today: "Today", beds: "Beds", tomorrow: "Tomorrow", sow: "Sow", demand: "Demand", impact: "Impact",
  report: "Simulation report", trail: "Trail",
};
export const SHARED_HINT = {
  beds: "What is growing, and how much is ready each day",
  tomorrow: "The most we can safely send, and who gets it",
  sow: "How many seedlings on the next sowing day, and why",
  demand: "Forecast per day with an honest band, and what moved it",
  trail: "Every day's decision as it stood that morning, with what came in that day",
};
