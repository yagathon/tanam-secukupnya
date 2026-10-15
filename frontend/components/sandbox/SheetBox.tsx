"use client";

import { useState } from "react";

/** "Paste from sheet" / "Copy as sheet" for one table. `parse` returns an error sentence, or null when applied;
 *  without it (a read-only table) there is only Copy. */
export default function SheetBox({ copy, parse, example }: {
  copy: () => string; parse?: (text: string) => string | null; example?: string;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<{ text: string; bad: boolean } | null>(null);
  const apply = () => {
    const err = parse?.(text) ?? null;
    setMsg(err ? { text: err, bad: true } : null);
    if (!err) { setText(""); setOpen(false); }
  };
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(copy());
      setMsg({ text: "Copied — paste it into a sheet.", bad: false });
    } catch {
      setMsg({ text: "The browser blocked the clipboard.", bad: true });
    }
  };
  return (
    <div className="sheet">
      <div className="row wrap">
        {parse && <button className="ghost small" onClick={() => setOpen(!open)}>{open ? "Close paste" : "Paste from sheet"}</button>}
        <button className="ghost small" onClick={doCopy}>Copy as sheet</button>
        {msg && <span className={`small ${msg.bad ? "bad" : "muted"}`}>{msg.text}</span>}
      </div>
      {open && parse && (
        <>
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={example} />
          <div className="row">
            <button className="primary small" disabled={!text.trim()} onClick={apply}>Replace the table</button>
            <span className="small muted">Columns copied from Sheets or Excel; a header row is fine.</span>
          </div>
        </>
      )}
    </div>
  );
}
