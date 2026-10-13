import type { Crop } from "@/lib/types";
import { lineKey } from "@/lib/series";

/** Segmented picker over every crop × demand line. */
export default function LinePicker({ crops, value, onChange }: {
  crops: Crop[];
  value: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="seg" role="tablist">
      {crops.flatMap((c) =>
        c.demand_lines.map((l) => {
          const k = lineKey(c.id, l.id);
          return (
            <button key={k} className={k === value ? "on" : ""} onClick={() => onChange(k)}>
              {c.name} <span className="muted">{l.id}</span>
            </button>
          );
        }),
      )}
    </div>
  );
}

export const firstLine = (crops: Crop[]) => lineKey(crops[0].id, crops[0].demand_lines[0].id);
