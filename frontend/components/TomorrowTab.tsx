"use client";

import type { TabProps } from "@/app/page";
import { kg, lineName, shortDate } from "@/lib/format";
import type { TomorrowLine } from "@/lib/types";

function LineTomorrow({ l }: { l: TomorrowLine }) {
  const short = l.short_kg > 0.005;
  return (
    <div className="card">
      <h2>{lineName(l.line)} · {shortDate(l.day)}</h2>
      <div className="kpis">
        <div><span className="small muted">Need</span><strong>{kg(l.need_kg)}</strong></div>
        <div><span className="small muted">Ready in range</span><strong>{kg(l.available_kg)}</strong></div>
        <div><span className="small muted">Max safe to send</span><strong>{kg(l.ceiling_kg)}</strong></div>
        <div><span className="small muted">Send</span><strong className={short ? "bad" : ""}>{kg(l.send_kg)}</strong></div>
      </div>
      <p className="small muted">
        Max safe = the most we can pick tomorrow without making any later day (until the next sowing is ready) shorter than
        it would be anyway.
      </p>
      {short && <p className="bad">Short {kg(l.short_kg)}: B2B minimums first, the rest pro-rata; households that were shorted least recently rotate out.</p>}

      <h3>Restaurants & caterers</h3>
      {l.buyers.length === 0 ? <p className="empty">No B2B orders for this line.</p> : (
        <div className="scroll">
          <table>
            <thead><tr><th>Buyer</th><th className="num">Ordered</th><th className="num">Minimum</th><th className="num">Served</th></tr></thead>
            <tbody>
              {l.buyers.map((b) => (
                <tr key={b.id}>
                  <td>{b.alias} {!b.known && <span className="pill muted" title="no order yet: the forecast stands in">forecast</span>}</td>
                  <td className="num">{kg(b.ordered_kg)}</td>
                  <td className="num">{kg(b.min_kg)}</td>
                  <td className={`num ${b.served_kg < b.ordered_kg - 0.005 ? "neg" : ""}`}>{kg(b.served_kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Households</h3>
      {l.households.length === 0 ? <p className="empty">No household deliveries tomorrow.</p> : (
        <ul className="signals">
          {l.households.map((h) => {
            const out = h.served_kg < h.ordered_kg - 0.005;
            return (
              <li key={h.id}>
                <span className={`pill ${out ? "down" : "up"}`}>{out ? (h.served_kg > 0 ? "partly" : "rotates out") : "served"}</span>{" "}
                {h.alias} <span className="muted small">{kg(h.served_kg)} of {kg(h.ordered_kg)}</span>
              </li>
            );
          })}
        </ul>
      )}

      {l.borrowing.length > 0 && (
        <>
          <h3>If we sent the full need anyway</h3>
          <p className="small muted">Picking more than the safe maximum borrows from later days:</p>
          <ul>{l.borrowing.map((b) => <li key={b.day} className="bad">borrowing from {shortDate(b.day)}: −{kg(b.kg)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function TomorrowTab({ data }: TabProps) {
  return <div className="grid">{data.tomorrow.lines.map((l) => <LineTomorrow key={l.line} l={l} />)}</div>;
}
