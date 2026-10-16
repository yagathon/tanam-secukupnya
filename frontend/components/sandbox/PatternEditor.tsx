"use client";

import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { pasteRow } from "@/lib/pattern";

/** A demand pattern as labelled cells with its bar chart under them: the shape is visible while typing.
 *  Pasting a spreadsheet row into any cell fills all of them. `flat` is the no-pattern value, drawn as a line. */
export default function PatternEditor({ labels, value, onChange, flat, target, unit = "%" }: {
  labels: string[]; value: number[]; onChange: (v: number[]) => void; flat: number; target?: number; unit?: string;
}) {
  const v = labels.map((_, i) => value[i] ?? flat);
  const sum = Math.round(v.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0) * 10) / 10;
  const off = target !== undefined && Math.abs(sum - target) > 0.5;
  return (
    <div className="pattern">
      <div className="cells" style={{ gridTemplateColumns: `repeat(${labels.length}, minmax(0, 1fr))` }}>
        {labels.map((l, i) => (
          <label key={l}>{l}
            <input type="number" step="any" min={0} value={Number.isFinite(v[i]) ? v[i] : ""}
              onChange={(e) => onChange(v.map((x, j) => (j === i ? (e.target.value === "" ? NaN : Number(e.target.value)) : x)))}
              onPaste={(e) => {
                const row = pasteRow(e.clipboardData.getData("text"), labels.length);
                if (row) { e.preventDefault(); onChange(row); }
              }} />
          </label>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <BarChart data={labels.map((l, i) => ({ l, v: Number.isFinite(v[i]) ? v[i] : 0 }))} margin={{ top: 6, right: 8, bottom: 0, left: -24 }}>
          <XAxis dataKey="l" fontSize={11} interval={0} />
          <YAxis fontSize={11} />
          <Tooltip formatter={(x) => [`${x}${unit}`, ""]} />
          <ReferenceLine y={flat} stroke="var(--muted)" strokeDasharray="4 3" />
          <Bar dataKey="v" fill="var(--leaf)" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <p className={`small ${off ? "bad" : "muted"}`}>
        Σ {sum}{target !== undefined && ` (needs ${target})`} · dashed line = flat ({Math.round(flat * 10) / 10}{unit})
      </p>
    </div>
  );
}

/** A 7-bar thumbnail of a buyer's week, for the buyer table. */
export function MiniBars({ value }: { value: number[] }) {
  const max = Math.max(...value, 1);
  return (
    <svg width="63" height="22" viewBox="0 0 63 22" aria-label={value.join(" ")}>
      {value.map((x, i) => {
        const h = Math.max(1, (x / max) * 20);
        return <rect key={i} x={i * 9} y={22 - h} width="7" height={h} fill="var(--leaf)" />;
      })}
    </svg>
  );
}
