// The sandbox, filled in by a visible browser: each day's rows from scenario.json are typed into the
// "Log the day" form, then "Next day →". Same rows as `scenario.py play`, which can take over after it.
//
// Runs on Windows (WSL has no browser libs):   cd tools\bot  &&  npm install   (once)
//   npm run bot -- --reset --days 14            clear the sandbox, load the scenario's setup, type 14 days
//   npm run bot -- --days 7 --pause 2000        continue from the sandbox's today, 2 s on each new day
//   npm run bot -- --ui https://tanam-secukupnya.web.app --reset --days 14     the same against prod
// Options: --ui http://localhost:3100  --api <default: :8100 for localhost, else the --ui origin>
//          --slow 120 (ms per action)  --channel chrome | msedge | chromium (Playwright's own build)
//          --scenario <path>  (default: scenario.json next to this file, else data/scenario/scenario.json)
// The browser profile is kept in ./profile, so the anonymous sign-in, and with it the sandbox, survives
// between runs. It is the bot's own sandbox: it never touches anyone else's. Delete ./profile for a new one.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0) return dflt;
  const v = process.argv[i + 1];
  return v === undefined || v.startsWith("--") ? true : v;
};
const UI = String(arg("ui", "http://localhost:3100")).replace(/\/+$/, "");
const local = /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(UI);
const API = `${arg("api", local ? "http://localhost:8100" : UI)}/api/sandbox`;
const DAYS = Number(arg("days", 14));
const PAUSE = Number(arg("pause", 1200));
const here = (f) => fileURLToPath(new URL(f, import.meta.url));
const scenarioPath = arg("scenario", existsSync(here("scenario.json")) ? here("scenario.json") : here("../../data/scenario/scenario.json"));
const scenario = JSON.parse(readFileSync(scenarioPath, "utf8"));

// The page signs in anonymously and sends a Firebase ID token on every API call; the bot reuses the latest one.
let token = "";
async function call(method, path, body) {
  const headers = { "content-type": "application/json" };
  if (token) headers.authorization = token;
  const r = await fetch(API + path, { method, headers, body: body && JSON.stringify(body) });
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

const byDay = {};
for (const r of scenario.rows) (byDay[r.date] ??= []).push(r);

const CHANNEL = arg("channel", "chrome");
const context = await chromium.launchPersistentContext(here("profile"), {
  channel: CHANNEL === "chromium" ? undefined : CHANNEL, headless: !!arg("headless", false),
  slowMo: Number(arg("slow", 120)), viewport: null, args: ["--start-maximized"],
});
const page = context.pages()[0] ?? (await context.newPage());
page.on("request", (r) => {
  const a = r.headers()["authorization"];
  if (r.url().includes("/api/") && a?.startsWith("Bearer ")) token = a;
});
// the page reloads its views after a log or a new day (trail is fetched last); a failed log does not reload
const reloaded = () => page.waitForResponse((r) => r.url().includes("/sandbox/trail"), { timeout: 60000 }).catch(() => null);
await page.goto(`${UI}/sandbox#today`);
for (let i = 0; !token && i < 120; i++) await page.waitForTimeout(500);
if (!token) throw new Error("the page made no signed-in API call within 60 s");
if (arg("reset", false)) {
  await call("POST", "/clear", { setup: true });
  await call("PUT", "/setup", scenario.setup);
  await page.reload();
}
await page.getByRole("heading", { name: "Log the day" }).waitFor({ timeout: 60000 });

const card = page.locator(".card", { has: page.getByRole("heading", { name: "Log the day" }) });
const grid = card.locator(".form-grid");
const WHO = { everyone: "everyone", businesses: "all businesses", households: "all households" };
const KIND = { order: "Order", sow: "Sow", loss: "Loss", signal: "Signal", postpone: "Postpone" };

async function fill(r, today) {
  await card.locator(".seg button", { hasText: new RegExp(`^${KIND[r.kind]}$`) }).click();
  if (r.kind === "order") {
    await grid.getByLabel("Buyer").selectOption({ label: r.buyer });
    await grid.getByLabel("Line").selectOption(r.line);
    await grid.getByLabel("kg (0 = no order this time)").fill(String(r.kg));
    await grid.getByLabel("For day").fill(r.for_day);
  } else if (r.kind === "sow") {
    await grid.getByLabel("Line").selectOption(r.line);
    if (String(r.seedlings ?? "plan").toLowerCase() === "plan") {
      const plan = (await call("GET", "/sow")).lines.find((l) => l.line === r.line);
      if (!plan || plan.day !== today || plan.seedlings <= 0) return false;   // the app plans no sowing today
    } else await grid.getByLabel("Seedlings").fill(String(r.seedlings));
  } else if (r.kind === "loss") {
    await grid.getByLabel("Line").selectOption(r.line);
    await grid.getByLabel("% lost").fill(String(r.pct));
    await grid.getByLabel("Cause").fill(r.cause ?? "");
  } else if (r.kind === "postpone") {
    await grid.getByLabel("Line").selectOption(r.line);
    await grid.getByLabel("Reason").fill(r.cause ?? "");
  } else if (r.kind === "signal") {
    await grid.getByLabel("Who").selectOption({ label: WHO[String(r.who ?? "everyone").toLowerCase()] ?? r.who });
    await grid.getByLabel("Line").selectOption(r.line ?? "");
    await grid.getByLabel(/^Effect %/).fill(String(r.effect_pct));
    await grid.getByLabel("From", { exact: true }).fill(r.from);
    await grid.getByLabel(/^To/).fill(r.to ?? "");
    await grid.getByLabel("Cause").fill(r.cause ?? "");
  }
  return true;
}

for (let n = 0; n < DAYS; n++) {
  const today = (await call("GET", "/today")).today;
  const rows = byDay[today] ?? [];
  if (today > scenario.rows.at(-1).date) break;
  console.log(`${today}: ${rows.length} row(s)`);
  for (const r of rows) {
    if (!(await fill(r, today))) { console.log(`  row ${r.row} ${r.kind}: skipped (no sowing planned today)`); continue; }
    const [res] = await Promise.all([page.waitForResponse((x) => x.url().includes("/sandbox/events")), reloaded(),
      card.getByRole("button", { name: "Log it" }).click()]);
    if (!res.ok()) console.log(`  row ${r.row} ${r.kind}: ${res.status()} ${await res.text()}`);
  }
  await page.waitForTimeout(PAUSE / 2);
  await Promise.all([reloaded(), page.getByRole("button", { name: "Next day →" }).click()]);
  await page.waitForTimeout(PAUSE / 2);
}
console.log(local ? "done; continue fast with: uv run --project backend python scripts/scenario.py play" : "done");
await page.waitForTimeout(3000);
await context.close();
