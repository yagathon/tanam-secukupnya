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
        <div><span className="small muted">Max to send</span><strong>{kg(l.ceiling_kg)}</strong></div>
        <div><span className="small muted">Send</span><strong className={short ? "bad" : ""}>{kg(l.send_kg)}</strong></div>
      </div>
      <p className="small muted">
        When the field can&apos;t cover every day until the next sowing is ready, tomorrow is served whole by borrowing
        plants meant for later days, as long as that debt stays within one average day of orders
        ({kg(l.debt_limit_kg)}). Past that, tomorrow is a market day: the field sends only what is safe and the rest is
        bought at the market, so the field catches up. The debt is recomputed every day, so it can heal by itself.
      </p>
      {l.debt_kg > 0.005 && !short && <p>Borrowed from later days: {kg(l.debt_kg)} of {kg(l.debt_limit_kg)}.</p>}
      {short && <p className="bad">Market day: buy {kg(l.short_kg)} at the market. From the field: B2B minimums first, the rest pro-rata; households that were shorted least recently rotate out.</p>}

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
          <h3>Borrowed from later days</h3>
          <p className="small muted">Tomorrow&apos;s send takes plants these days would have had:</p>
          <ul>{l.borrowing.map((b) => <li key={b.day} className="bad">borrowing from {shortDate(b.day)}: −{kg(b.kg)}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function TomorrowTab({ data }: TabProps) {
  return <div className="grid">{data.tomorrow.lines.map((l) => <LineTomorrow key={l.line} l={l} />)}</div>;
}
