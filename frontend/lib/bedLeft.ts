/** What the app thinks is still standing in a bed, so the farmer can match it against what they see. */
export function bedLeftText(
  b: { label: string; seedlings: number; plants_left: number; avg_g: number | null }, survival: number,
): string {
  if (b.plants_left <= 0) return `App estimate for ${b.label}: empty.`;
  const pct = Math.round((b.plants_left / (b.seedlings * survival)) * 100);
  const head = `App estimate for ${b.label}: ~${b.plants_left} plants left (~${pct}% of full)`;
  if (b.avg_g == null) return `${head}.`;
  return `${head} ≈ ${((b.plants_left * b.avg_g) / 1000).toFixed(1)} kg at ~${b.avg_g} g a plant.`;
}
