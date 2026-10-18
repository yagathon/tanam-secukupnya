"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { Api } from "@/lib/api";
import { friendly, int, lineName, shortDate } from "@/lib/format";
import type { DemoSetup } from "@/lib/types";

const DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const days = (w: number[]) => (w.length === 7 ? "every day" : w.map((d) => DAY[d]).join(", "));

/** The demo farm as it started: the same for every visitor, so it is shown, not edited. */
export default function DemoSetupTab({ api }: { api: Api }) {
  const [s, setS] = useState<DemoSetup | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.demoSetup().then(setS).catch((e) => setError(friendly(e)));
  }, [api]);
  if (error) return <div className="card error">{error}</div>;
  if (!s) return <div className="card muted">Loading the setup…</div>;

  const c = s.crop;
  const hh = Object.entries(
    s.households.reduce<Record<string, { n: number; kg: number }>>((acc, h) => {
      const k = `${h.line}|${days(h.weekdays)}`;
      acc[k] = { n: (acc[k]?.n ?? 0) + 1, kg: (acc[k]?.kg ?? 0) + h.kg };
      return acc;
    }, {}),
  ).sort();

  return (
    <div className="grid">
      <div className="card">
        <h2>Read-only</h2>
        <p className="small">
          The demo farm starts the same for every visitor on {shortDate(s.day0)}, so the story is the same for everyone.
          {s.synthetic && " Synthetic data: aliases only."} To enter your own crop, buyers and beds, use the{" "}
          <Link href="/sandbox">Sandbox →</Link>
        </p>
      </div>
      <div className="card">
        <h2>Crop: {c.name}</h2>
        <div className="scroll">
          <table>
            <tbody>
              <tr><td>Nursery</td><td className="num">{c.nursery_days} days</td></tr>
              <tr><td>Germination · survival in bed</td><td className="num">{Math.round(c.germination * 100)}% · {Math.round(c.survival * 100)}%</td></tr>
              <tr><td>Longest in bed</td><td className="num">{c.max_bed_day} days</td></tr>
              <tr><td>Sowing days</td><td className="num">{days(c.sow_weekdays)}</td></tr>
              {c.lines.map((l) => (
                <tr key={l.id}><td>{lineName(l.id)}</td><td className="num">{l.min_g}–{l.max_g} g · {l.channels.join(", ")}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Buyers ({s.buyers.length} businesses)</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Buyer</th><th>Type</th><th>Order days</th><th className="num">Usual kg / order</th></tr></thead>
            <tbody>
              {s.buyers.map((b) => (
                <tr key={b.id}>
                  <td>{b.alias}</td><td>{b.segment}</td><td>{days(b.weekdays)}</td>
                  <td className="num">{Object.entries(b.lines).map(([l, x]) => `${x.kg} (${l}, min ${x.min_kg})`).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Households ({s.households.length} subscriptions)</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Line</th><th>Delivery days</th><th className="num">Households</th><th className="num">kg per delivery</th></tr></thead>
            <tbody>
              {hh.map(([k, v]) => {
                const [line, when] = k.split("|");
                return <tr key={k}><td>{line}</td><td>{when}</td><td className="num">{v.n}</td><td className="num">{v.kg.toFixed(1)}</td></tr>;
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Beds growing on day 0 ({s.beds.length})</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Bed</th><th>Line</th><th>Sown</th><th className="num">Seedlings</th></tr></thead>
            <tbody>
              {s.beds.map((b) => (
                <tr key={b.id}><td>{b.label}</td><td>{b.line}</td><td>{shortDate(b.sown_on)}</td><td className="num">{int(b.seedlings)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>The fixed farmer (the comparison)</h2>
        <p className="small">
          Before Tanam, the farm sowed the same count every {s.fixed.weekdays.map((d) => DAY[d]).join(" & ")}:{" "}
          {Object.entries(s.fixed.seedlings).map(([l, n]) => `${int(n)} ${l}`).join(" + ")} seedlings, sized from the
          history&apos;s average demand. Impact and the Simulation report compare Tanam against it.
        </p>
      </div>
    </div>
  );
}
