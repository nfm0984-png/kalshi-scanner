import React, { useEffect, useMemo, useState, type ReactNode } from "react";
import BAKED_LAST20 from "./last20.json";

const NAVY = "#1B1233";
const NAVY_DEEP = "#11081F";
const BLUE = "#5B21B6";
const BLUE_BRIGHT = "#5B21B6";
const BLUE_SOFT = "#EDE9FE";
const BLUE_INK = "#5B21B6";
const PAGE = "#F5F3FF";
const GREEN = "#15803D";
const RED = "#B91C1C";
const AMBER = "#B45309";
const TARGET_FOLLOW = 100;
interface Last20 { dots: string; w: number; l: number; n: number; pnl: number }
function capperDatabase(): CapperDatabase {
  const fol = DATA.following || {};
  const db = fol.database || {};
  const rows = db.cappers && db.cappers.length ? db.cappers : (fol.cappers || []).map((c: FollowCapper, i: number) => ({ rank: c.rank || (i + 1), nickname: c.nickname, w: c.closedW, l: c.closedL, n: c.closedN, pnl: c.pnl, recordLine: c.recordLine, manual: c.manual }));
  return { target: db.target || TARGET_FOLLOW, size: db.size != null ? db.size : rows.length, updatedAt: db.updatedAt, note: db.note, cappers: rows };
}
function dbRankOf(name: string): number {
  const rows = capperDatabase().cappers || [];
  const k = (name || "").toLowerCase();
  const hit = rows.find((c: CapperDbRow) => (c.nickname || "").toLowerCase() === k);
  if (hit && hit.rank) return hit.rank;
  const i = rows.findIndex((c: CapperDbRow) => (c.nickname || "").toLowerCase() === k);
  return i >= 0 ? i + 1 : 9999;
}
function bestDbRank(backers: Backer[]): number {
  let best = 9999;
  (backers || []).forEach((b: Backer) => { if (isFollowedBacker(b)) best = Math.min(best, dbRankOf(b.name)); });
  return best;
}

const ELITE_MIN_BETS = 10;
const FRESH_SECS = 3 * 3600;
const FRESH_MIN = 500;
const MIN_STAKE = 1000;
const MIN_STAKE_COMBO = 1000;
const DECIDED_PX = 0.97;
const KFINAL = ["finalized", "determined", "settled"];
const FINISH_GRACE_SECS = 30 * 60;
const LIVE_HOURS: Record<string, number> = { NFL: 4, CFB: 4, NCAAF: 4, MLB: 3.5, ATP: 3.5, WTA: 3.5, TENNIS: 3.5, UFC: 6, MMA: 6, BOXING: 6, CBB: 2.75, NCAAB: 2.75, NCAAMB: 2.75, NBA: 3, NHL: 3, CS2: 3.5, DOTA2: 3.5, LOL: 3.5, VAL: 3.5, ESPORTS: 3.5 };
const liveSecsFor = (league?: string | null): number => Math.round(3600 * (LIVE_HOURS[(league || "").toUpperCase()] || 3));
const BT_ORDER = ["Combo", "Moneyline", "Spread", "Totals", "Both teams to score", "Player props", "Other"];

interface WL { w: number; l: number; n?: number }
interface ComboLeg { ticker: string; eventTicker?: string; yesNo: string; backing?: string; game?: string; marketTitle?: string; contractTitle?: string; matchup?: string; startTs?: number; closeTs?: number; league?: string; url?: string }
interface KalshiView { backing?: string; marketTitle?: string; outcome?: string; yesNo: "Yes" | "No" | null; price: number | null; ticker: string | null; comboUrl?: string | null }
interface SportRec { n: number; w: number; l: number; roi?: number | null; profit?: number }
interface Backer { name: string; cost: number; avg?: number | null; line: string; rec?: WL | null; sportRec?: WL | null; bestAt?: string | null; pnl?: number | null; pinned?: boolean; lastTs?: number | null; lastSeen?: string; lastSeenTs?: number | null; tier?: string; addedTs?: number | null; addedLastTs?: number | null }
interface Pick { key: string; ticker: string; eventTicker?: string; mid: string; bt: string; big: string; sub: string; view: KalshiView; backers: Backer[]; total: number; tags: string[]; slip?: number | null; startTs: number; state: string; status?: string; result?: string | null; closeTs?: number; yesAsk?: number | null; noAsk?: number | null; isCombo?: boolean; legs?: ComboLeg[]; comboUrl?: string | null; payout?: number | null }
interface Game { id: string; game: string; league: string; startTs: number; start: string; live: boolean; state: string; picks: Pick[]; closeTs?: number }
interface Capper { nickname: string; profileUrl?: string; tier: string; pinned?: boolean; tag?: string; ranks?: Record<string, number>; profitRanks?: Record<string, any>; onProfitBoard?: boolean; pnl?: number | null; pnlSource?: string | null; weeklyPnl?: number | null; monthlyPnl?: number | null; yearlyPnl?: number | null; tape7d?: number | null; tape30d?: number | null; volumeUsd?: number | null; ageDays?: number | null; graded?: { n: number; w: number; l: number; roi: number | null; profit: number; sample?: string; formW?: number; formL?: number } | null; gradedAll?: { n: number; w: number; l: number; roi: number | null; profit: number; sample?: string } | null; sports?: Record<string, SportRec>; bestAt?: string | null; recordLine: string; pickCount: number; followCount?: number; rejectNote?: string; positionsVisible?: boolean; postsVisible?: boolean; pickSource?: string; openPositions?: number; lastTs?: number | null }
interface SideCmp { verdict: "this" | "other" | null; thisBest: WL; oppBest: WL; thisName: string; oppName: string }
interface FollowPick { ticker: string; eventTicker?: string; game: string; backing?: string; label?: string; yesNo: "Yes" | "No" | string; entry?: number | null; price?: number | null; yesAsk?: number | null; noAsk?: number | null; cost?: number | null; contracts?: number | null; startTs: number; closeTs?: number; state?: string; status?: string; result?: string | null; league?: string; bt?: string; nickname: string; recordLine?: string; tier?: string; marketTitle?: string; contractTitle?: string; lastTs?: number | null; slip?: number | null; lastSeen?: string; lastSeenTs?: number | null; addedTs?: number | null; addedLastTs?: number | null; source?: string; isCombo?: boolean; legs?: ComboLeg[]; comboUrl?: string | null; payout?: number | null }
interface FollowCapper { nickname: string; w: number; l: number; p?: number; n: number; hitPct: number | null; open: number; hidden?: boolean; pnl?: number | null; roi?: number | null; pickSource?: string; positionsVisible?: boolean; postsVisible?: boolean; openPositions?: number; closedW?: number; closedL?: number; closedN?: number; formW?: number; formL?: number; recordLine?: string; profileUrl?: string; rank?: number; manual?: boolean }
interface CapperDbRow { rank: number; nickname: string; w?: number; l?: number; n?: number; pnl?: number | null; recordLine?: string; manual?: boolean }
interface CapperDatabase { target?: number; size?: number; updatedAt?: string; note?: string; cappers?: CapperDbRow[] }
interface Following { startedAt?: string; startedTs?: number; cappers?: FollowCapper[]; picks?: FollowPick[]; recorded?: number; graded?: number; database?: CapperDatabase }
interface ScanHist { ts: number; at: string; names?: number; newFollows?: string[]; followed?: number; target?: number; openPicks?: number; ids?: string[] }
interface Data { scannedAt: string; ts: number; followCheckedAt?: string; source?: { note?: string; periodUsed?: string; coverage?: any; db?: { active?: number; queue?: number; rejected?: number; pinned?: number } }; cappers?: Capper[]; games?: Game[]; following?: Following; scanHistory?: ScanHist[]; scannerRecord?: { minN?: number; updatedTs?: number; cappers?: Record<string, { name?: string; n: number; w: number; l: number; units: number; roi?: number | null; cold?: boolean; last20?: Last20 }> }; comboRecords?: { minN?: number; updatedTs?: number; cappers?: Record<string, { name?: string; n: number; w: number; l: number; pnl: number; boost?: boolean }> } }

let DATA: Data = ((window as any).__DATA || { scannedAt: "", ts: 0, cappers: [], games: [] }) as Data;
const SCAN_WORKFLOW_URL = "https://github.com/nfm0984-png/kalshi-scanner/actions/workflows/scanner.yml";
const CFG: any = (window as any).__CFG || {};
const GH_OWNER = String(CFG.owner || "nfm0984-png");
const GH_REPO = String(CFG.repo || "kalshi-scanner");
const GH_WORKFLOW = String(CFG.workflow || "scanner.yml");
const KEY_LS = "kalshi-scanner-gh-key";
const SCAN_EXPECT_SECS = 150;
function accessKey(): string {
  const built = (CFG.k || []).map((x: string) => x.split("").reverse().join("")).join("");
  if (built) return built;
  try { const v = window.localStorage.getItem(KEY_LS); if (v) return v.trim(); } catch (e) { /* ignore */ }
  return "";
}
function ghApi(path: string, init?: { method?: string; body?: string; repo?: string }): Promise<Response> {
  const repo = (init && init.repo) || GH_REPO;
  const h: Record<string, string> = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", Authorization: "Bearer " + accessKey() };
  if (init && init.body) h["Content-Type"] = "application/json";
  return fetch("https://api.github.com/repos/" + GH_OWNER + "/" + repo + path, { method: (init && init.method) || "GET", body: init && init.body, headers: h, cache: "no-store" });
}
function pageAssetUrl(name: string): string {
  try {
    let path = window.location.pathname || "/";
    if (path.endsWith(".html")) path = path.replace(/[^/]+$/, "");
    if (!path.endsWith("/")) path += "/";
    return window.location.origin + path + name;
  } catch (e) {
    return name;
  }
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const mmss = (sec: number): string => Math.floor(sec / 60) + ":" + String(Math.floor(sec % 60)).padStart(2, "0");
interface Job { mode: "scan" | "refresh"; phase: string; msg: string; t0: number; url?: string }

function formatNowPt(ms = Date.now()): string {
  return new Date(ms).toLocaleString("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" }) + " PT";
}
function formatLongDatePt(ms = Date.now()): string {
  return new Date(ms).toLocaleDateString("en-US", { timeZone: "America/Los_Angeles", weekday: "long", month: "long", day: "numeric" });
}
function nextScheduledPt(ms = Date.now()): string {
  const parts: Record<string, string> = {};
  new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(ms)).forEach((p) => { if (p.type !== "literal") parts[p.type] = p.value; });
  let year = +parts.year, month = +parts.month, day = +parts.day, hour = +parts.hour;
  if (+parts.minute >= 20) {
    hour += 1;
    if (hour >= 24) {
      hour = 0;
      const next = new Date(Date.UTC(year, month - 1, day) + 86400000);
      year = next.getUTCFullYear();
      month = next.getUTCMonth() + 1;
      day = next.getUTCDate();
    }
  }
  const ampm = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return h12 + ":20 " + ampm + " PT";
}
async function unlockRawData(raw: any): Promise<Data> {
  const unlock = (window as any).__unlockData as undefined | ((raw: any) => Promise<Data>);
  if (unlock) return await unlock(raw);
  if (raw && raw.enc) throw new Error("Unlock this device to refresh.");
  return raw as Data;
}
async function fetchPagesData(): Promise<any> {
  const url = pageAssetUrl("data.json") + "?t=" + Date.now() + "&n=" + Math.random().toString(36).slice(2);
  const r = await fetch(url, { cache: "no-store", headers: { "Cache-Control": "no-cache", Pragma: "no-cache" } });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return await r.json();
}
async function fetchGithubData(): Promise<any> {
  // GitHub Pages caches data.json for 10 minutes and often ignores query-string busts.
  // The Contents API is a public, CORS-open read of the same encrypted file on main.
  const url = "https://api.github.com/repos/" + GH_OWNER + "/" + GH_REPO + "/contents/data.json?ref=main&t=" + Date.now();
  const h: Record<string, string> = { Accept: "application/vnd.github.raw+json", "X-GitHub-Api-Version": "2022-11-28" };
  const key = accessKey();
  if (key) h.Authorization = "Bearer " + key;
  const r = await fetch(url, { cache: "no-store", headers: h });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return await r.json();
}
async function fetchLatestData(): Promise<Data> {
  let raw: any = null;
  let lastErr: any = null;
  try { raw = await fetchGithubData(); } catch (e) { lastErr = e; }
  if (!raw) {
    try { raw = await fetchPagesData(); } catch (e) { lastErr = e; }
  }
  if (!raw) {
    const loader = (window as any).__loadScannerData as undefined | (() => Promise<Data>);
    if (loader) return await loader();
    throw lastErr || new Error("Couldn't refresh.");
  }
  try {
    return await unlockRawData(raw);
  } catch (e: any) {
    const msg = String((e && e.message) || e || "");
    if (/unlock/i.test(msg)) throw e;
    throw new Error("Couldn't decrypt the new data. Unlock this device and try again.");
  }
}

const money = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  const cts = Math.round(a * 100);
  // Show cents whenever the tape is not a whole dollar, so $1.84 is not $2.
  const frac = cts % 100 === 0 && a >= 100 ? 0 : 2;
  return s + "$" + a.toLocaleString("en-US", { minimumFractionDigits: frac, maximumFractionDigits: 2 });
};
const kMoney = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(a >= 1e7 ? 1 : 2).replace(/\.0$/, "") + "M";
  if (a >= 10000) return s + "$" + (a / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return money(n);
};
const cents = (px: number | null | undefined): string => {
  if (px == null || px <= 0) return "—";
  const x = Math.round((1 / Math.min(px, 1)) * 10) / 10;
  return x.toFixed(1).replace(/\.0$/, "") + "x";
};
const payoutOf = (p: Pick): number => (p.view.price ? Math.round((1 / Math.min(p.view.price, 1)) * 10) / 10 : 99);
const ptTime = (ts: number): string => new Date(ts * 1000).toLocaleString("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PT";
const ptDayKey = (ts: number): string => new Date(ts * 1000).toLocaleDateString("en-US", { timeZone: "America/Los_Angeles" });
const ptClock = (ts: number): string => new Date(ts * 1000).toLocaleTimeString("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" });
const addedWhen = (ts: number, now: number): string => {
  if (ptDayKey(ts) === ptDayKey(now)) return ptClock(ts) + " PT";
  if (ptDayKey(ts) === ptDayKey(now - 86400)) return "yesterday " + ptClock(ts) + " PT";
  return new Date(ts * 1000).toLocaleString("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "short", day: "numeric" }) + ", " + ptClock(ts) + " PT";
};
function AddedChip(props: { backers?: Backer[]; addedTs?: number | null; addedLastTs?: number | null; now: number }): React.ReactElement | null {
  const bs = props.backers || [];
  const firsts = bs.map((b: Backer) => b.addedTs || 0).filter((x: number) => x > 0);
  if (props.addedTs) firsts.push(props.addedTs);
  if (!firsts.length) return null;
  const first = Math.min(...firsts);
  const lasts = bs.map((b: Backer) => b.addedLastTs || 0).concat([props.addedLastTs || 0]);
  const last = Math.max(...lasts);
  const more = last > first + 300 ? (" · added to " + (ptDayKey(last) === ptDayKey(first) ? ptClock(last) : addedWhen(last, props.now))) : "";
  return <span data-added-ts={String(first)} title="When this pick first showed up on the scanner" style={{ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: "#EDE9FE", color: "#4C1D95", border: "1.5px solid #A78BFA", fontSize: 12, fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{"🕒 Added " + addedWhen(first, props.now) + more}</span>;
}
const untilText = (ts: number, now: number): string => {
  const m = Math.max(0, Math.round((ts - now) / 60));
  return m < 60 ? m + " min" : Math.floor(m / 60) + "h " + (m % 60 ? (m % 60) + "m" : "");
};
const ago = (ts: number, now: number): string => {
  const s = Math.max(0, now - ts);
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
};
const signedK = (n: number): string => (n >= 0 ? "+" : "-") + kMoney(Math.abs(n)).slice(n >= 0 ? 0 : 0).replace(/^\$/, "$");
const wlRate = (r: WL): number => (r.w + r.l ? r.w / (r.w + r.l) : 0);
const wlBetter = (a: WL, b: WL): boolean => {
  const big = (r: WL) => (r.w + r.l >= ELITE_MIN_BETS ? 1 : 0);
  if (big(a) !== big(b)) return big(a) > big(b);
  return (wlRate(a) - wlRate(b) > 1e-9) || (Math.abs(wlRate(a) - wlRate(b)) <= 1e-9 && a.w > b.w);
};
const wlText = (r: WL): string => r.w + "-" + r.l;
const pctText = (x: number): string => Math.round(x * 100) + "%";
const eventTickerOf = (ticker: string | null): string | null => {
  if (!ticker) return null;
  const i = ticker.lastIndexOf("-");
  return i > 0 ? ticker.slice(0, i) : ticker;
};
const comboShareUrl = (ticker: string | null | undefined, yesNo?: string | null): string | null => {
  if (!ticker || ticker.toUpperCase().indexOf("KXMVE") !== 0) return null;
  const side = (yesNo || "yes").toLowerCase() === "no" ? "no" : "yes";
  return "https://kalshi.com/combos?marketTicker=" + encodeURIComponent(ticker) + "&side=" + side;
};
const kalshiUrlOf = (ticker: string | null | undefined, comboUrl?: string | null, yesNo?: string | null): string | null => {
  // Prefer the ticker-based combo share URL. Older comboUrl values pointed at
  // /markets/{series}/{slug}/{event}, which Kalshi 307s to an empty /combos builder.
  const share = comboShareUrl(ticker, yesNo);
  if (share) return share;
  if (comboUrl && comboUrl.indexOf("marketTicker=") >= 0) return comboUrl;
  // Singles: /markets_by_ticker/{MARKET} is a path the Kalshi iPhone app claims
  // (apple-app-site-association) and on web it 200s to the market page with that
  // contract pre-selected. The old /markets/{event} short form 404s on web.
  return marketByTickerUrl(ticker);
};
function marketByTickerUrl(ticker: string | null | undefined): string | null {
  const t = (ticker || "").trim();
  return t ? "https://kalshi.com/markets_by_ticker/" + encodeURIComponent(t.toUpperCase()) : null;
}
const legUrlOf = (leg: ComboLeg): string | null => marketByTickerUrl(leg.ticker) || leg.url || null;
const isComboPick = (p: { isCombo?: boolean; ticker?: string; legs?: ComboLeg[]; bt?: string; comboUrl?: string | null }): boolean => {
  return !!(p.isCombo || (p.legs && p.legs.length >= 2) || p.bt === "Combo" || (p.ticker || "").toUpperCase().indexOf("KXMVE") === 0);
};
function copyText(text: string): void {
  try { if (navigator.clipboard && navigator.clipboard.writeText) { void navigator.clipboard.writeText(text); return; } } catch (e) {}
  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "true");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  } catch (e) {}
}
function matchupOf(...vals: Array<string | null | undefined>): string {
  // "Ole Miss vs Clemson: 1st Half Spread" -> "Ole Miss vs Clemson"
  for (let i = 0; i < vals.length; i++) {
    const raw = (vals[i] || "").trim();
    if (!raw) continue;
    const head = raw.split(":")[0].trim();
    if (/\bvs\.?\b/i.test(head) && head.length >= 5 && head.length <= 90) return head;
  }
  return "";
}
function legPickLabel(leg: ComboLeg): string {
  const line = (leg.contractTitle || leg.backing || leg.ticker || "").trim();
  return ((leg.yesNo || "") + (line ? " · " + line : "")).trim();
}
function MatchupLine(props: { matchup?: string; startTs?: number; now?: number }): React.ReactElement | null {
  const mu = props.matchup || "";
  const start = props.startTs || 0;
  if (!mu && !start) return null;
  const live = !!(start && props.now && start <= props.now);
  const bits = [mu, start ? ((live ? "Started " : "") + ptTime(start)) : ""].filter(Boolean);
  return <div data-matchup="1" style={{ fontSize: 13, lineHeight: "18px", fontWeight: 650, color: "#475569", marginTop: 2, overflowWrap: "anywhere" }}>{bits.join(" · ")}</div>;
}

function comboLegsText(p: { backing?: string; game?: string; yesNo?: string; cost?: number | null; price?: number | null; comboUrl?: string | null; ticker?: string; legs?: ComboLeg[] }): string {
  const legs = p.legs || [];
  const lines: string[] = [
    "Kalshi combo" + (p.game ? (" · " + p.game) : ""),
    (p.backing || "") + (p.yesNo ? (" · " + p.yesNo) : ""),
    p.cost != null ? ("Stake $" + Math.round(p.cost * 100) / 100) : "",
    p.price != null ? ("Price " + p.price + " · pays " + cents(p.price)) : "",
    p.comboUrl || kalshiUrlOf(p.ticker || null) || "",
    "",
    "Legs:",
  ];
  legs.forEach((leg: ComboLeg, i: number) => {
    const start = leg.startTs ? ptTime(leg.startTs) : "";
    const mu = matchupOf(leg.matchup, leg.game, leg.marketTitle);
    lines.push((i + 1) + ". " + legPickLabel(leg) + (mu ? (" · " + mu) : "") + (start ? (" · " + start) : "") + (legUrlOf(leg) ? (" · " + legUrlOf(leg)) : ""));
  });
  return lines.filter((x) => x !== "").join("\n");
}
function ComboBlock(props: {
  legs?: ComboLeg[];
  now: number;
  ticker?: string | null;
  comboUrl?: string | null;
  yesNo?: string | null;
  price?: number | null;
  payout?: number | null;
  stake?: number | null;
  backers?: Backer[];
  copyPayload?: string;
}): React.ReactElement | null {
  const legs = props.legs || [];
  if (!legs.length && !isComboPick({ ticker: props.ticker || undefined, comboUrl: props.comboUrl, legs: props.legs })) return null;
  const href = kalshiUrlOf(props.ticker, props.comboUrl, props.yesNo);
  const n = legs.length;
  const yes = (props.yesNo || "Yes") !== "No";
  const pay = props.payout && props.payout > 0 ? props.payout : (props.price && props.price > 0 ? 1 / Math.min(props.price, 1) : null);
  // Never show "Combo · 0 legs" — if legs did not attach, say they are loading.
  const comboLabel = n > 0 ? ("Combo · " + n + " legs") : "Combo · legs loading";
  return (
    <div data-combo-card="1" style={{ marginTop: 10, padding: "12px 14px 14px", borderRadius: 16, border: "1.5px solid #C4B5FD", background: "linear-gradient(180deg, #F5F3FF 0%, #FFFFFF 42%)" }}>
      <div style={{ fontSize: 11, fontWeight: 850, letterSpacing: "0.08em", textTransform: "uppercase", color: "#5B21B6" }}>{comboLabel}</div>
      {(props.backers || []).map((b: Backer) => {
        const cap = capperOf(b.name);
        const fromBacker = b.rec && (b.rec.w + b.rec.l) > 0 ? { w: b.rec.w, l: b.rec.l, roi: (cap ? (cap.graded && cap.graded.roi != null ? cap.graded.roi : capperRoiPct(cap.nickname).roi) : null) as number | null } : null;
        const fromDb = gradedWL(cap);
        const g = fromBacker || (fromDb && (fromDb.w + fromDb.l) > 0 ? { w: fromDb.w, l: fromDb.l, roi: fromDb.roi } : null);
        const pnl = cap && cap.pnl != null ? cap.pnl : null;
        return (
          <div key={b.name} data-combo-capper={b.name} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
            <Face name={b.name} size={28} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 15, fontWeight: 850, color: NAVY }}>{b.name}</span>
                {g ? <RecordPill w={g.w} l={g.l} roi={g.roi} /> : <RecordPill w={0} l={0} />}
                {pnl != null ? <Chip bg={pnl >= 0 ? "#DCFCE7" : "#FEE2E2"} color={pnl >= 0 ? GREEN : RED}>{(pnl >= 0 ? "+" : "") + kMoney(pnl)}</Chip> : null}
                {b.tier ? <TierChip tier={b.tier} /> : null}
              </div>
              <Last20Dots name={b.name} />
            </div>
          </div>
        );
      })}
      {n ? (
        <ol data-combo-legs="1" style={{ margin: "10px 0 0", padding: "0 0 0 18px" }}>
          {legs.map((leg: ComboLeg, i: number) => {
            const legHref = legUrlOf(leg);
            const mu = matchupOf(leg.matchup, leg.game, leg.marketTitle);
            return (
              <li key={(leg.ticker || "leg") + "|" + i} style={{ marginTop: 8, fontSize: 14, lineHeight: "19px", color: NAVY }}>
                <div style={{ fontWeight: 800 }}>{legPickLabel(leg)}</div>
                <MatchupLine matchup={mu} startTs={leg.startTs} now={props.now} />
                {legHref ? <a data-leg-link="1" href={legHref} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 4, padding: "4px 10px", borderRadius: 999, border: "1.5px solid #C4B5FD", background: "#FFFFFF", fontSize: 13, fontWeight: 800, color: "#5B21B6", textDecoration: "none" }}>Open leg ↗</a> : null}
              </li>
            );
          })}
        </ol>
      ) : null}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
        {props.stake != null && props.stake > 0 ? <span style={{ fontSize: 24, lineHeight: "28px", fontWeight: 900, fontVariantNumeric: "tabular-nums", color: NAVY }}>{kMoney(props.stake)}</span> : null}
        <span style={{ fontSize: 13, fontWeight: 800, color: "#64748B" }}>Stake</span>
        {pay ? <span style={{ fontSize: 16, fontWeight: 850, color: yes ? GREEN : RED }}>{(props.yesNo || "Yes") + " · pays " + (Math.round(pay * 10) / 10) + "x"}</span> : (props.price != null ? <span style={{ fontSize: 16, fontWeight: 850, color: yes ? GREEN : RED }}>{(props.yesNo || "Yes") + " · pays " + cents(props.price)}</span> : null)}
      </div>
      {href ? (
        <>
        <a data-combo-link="1" href={href} target="_blank" rel="noreferrer" style={{ display: "block", marginTop: 12, textAlign: "center", padding: "12px 14px", borderRadius: 14, background: "#5B21B6", color: "#FFFFFF", fontSize: 16, fontWeight: 900, textDecoration: "none" }}>Open combo on Kalshi ↗</a>
        <div style={{ marginTop: 8, fontSize: 12, fontWeight: 650, color: "#6B21A8", textAlign: "center", lineHeight: "16px" }}>On iPhone, if the combo doesn’t load in the Kalshi app, tap each leg’s “Open leg ↗” above and add it to your combo ticket.</div>
        </>
      ) : (
        <div style={{ marginTop: 10, fontSize: 12, fontWeight: 650, color: "#6B21A8" }}>
          {"Tap each leg’s “Open leg ↗” above to add it to your combo ticket, or "}
          <button type="button" data-copy-legs="1" onClick={() => copyText(props.copyPayload || "")} style={{ border: "none", background: "none", padding: 0, fontSize: 12, fontWeight: 800, color: "#5B21B6", cursor: "pointer" }}>copy them all</button>
          {"."}
        </div>
      )}
    </div>
  );
}

function Chip(props: { bg: string; color: string; children: ReactNode }) {
  return <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: props.bg, color: props.color, fontSize: 11, fontWeight: 850 }}>{props.children}</span>;
}
function Text(props: { children: ReactNode }) {
  return <p style={{ fontSize: 14, lineHeight: "20px", color: "#334155", margin: "0 2px 12px" }}>{props.children}</p>;
}
function EmptyState(props: { title: string; body: string }) {
  return (
    <div style={{ padding: "18px 14px", borderRadius: 16, border: "1.5px dashed #C4B5FD", background: "#FFFFFF", margin: "8px 0 12px" }}>
      <div style={{ fontSize: 16, fontWeight: 850, color: NAVY }}>{props.title}</div>
      <div style={{ fontSize: 14, color: "#475569", marginTop: 4 }}>{props.body}</div>
    </div>
  );
}
function Section(props: { heading: string; caption?: string; children: ReactNode }) {
  return (
    <section style={{ margin: "8px 0 18px" }}>
      <h2 style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-0.02em", color: NAVY, margin: "0 2px 2px" }}>{props.heading}</h2>
      {props.caption ? <div style={{ fontSize: 13, fontWeight: 650, color: "#475569", margin: "0 2px 10px" }}>{props.caption}</div> : null}
      {props.children}
    </section>
  );
}

const AVATARS = ["#1D4ED8", "#0284C7", "#0F766E", "#1E3A8A", "#0369A1", "#4338CA"];
const initials = (n: string): string => {
  const parts = n.replace(/[^A-Za-z0-9 \-_]/g, "").split(/[\s\-_]+/).filter((x: string) => x.length > 0);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return n.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?";
};
const hue = (n: string): string => {
  let h = 0;
  for (let i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) % 997;
  return AVATARS[h % AVATARS.length];
};
function Face(props: { name: string; size?: number }) {
  const s = props.size || 40;
  return (
    <span data-face={props.name} style={{ width: s, height: s, borderRadius: 999, background: hue(props.name), color: "#FFFFFF", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: s * 0.38, fontWeight: 800, flex: "none", letterSpacing: "-0.02em" }}>{initials(props.name)}</span>
  );
}
function capperOf(name: string): Capper | undefined {
  const k = (name || "").toLowerCase();
  return (DATA.cappers || []).find((c: Capper) => (c.nickname || "").toLowerCase() === k);
}
const QUALITY_SEVEN_SECS = 7 * 86400;
function qualityNum(v: unknown): number | null {
  return typeof v === "number" && isFinite(v) ? v : null;
}
function qualityTs(v: unknown, now: number): number | null {
  let n = typeof v === "number" && isFinite(v) ? v : null;
  if (n == null) return null;
  if (n > 1e12) n = n / 1000;
  if (n < 1e9 || n > now + 86400) return null;
  return n;
}
function capperLastTsMap(now: number): Record<string, number> {
  const m: Record<string, number> = {};
  const bump = (name: string | undefined, ts: unknown) => {
    const k = (name || "").toLowerCase();
    const t = qualityTs(ts, now);
    if (!k || t == null) return;
    if (m[k] == null || t > m[k]) m[k] = t;
  };
  (DATA.cappers || []).forEach((c: Capper) => bump(c.nickname, c.lastTs));
  (DATA.games || []).forEach((g: Game) => (g.picks || []).forEach((p: Pick) => (p.backers || []).forEach((b: Backer) => { bump(b.name, b.lastTs); bump(b.name, b.lastSeenTs); })));
  ((DATA.following && DATA.following.picks) || []).forEach((fp: FollowPick) => bump(fp.nickname, fp.lastTs));
  return m;
}
function capperQualityOk(name: string | undefined, now: number, lastMap?: Record<string, number>): boolean {
  const c = capperOf(name || "");
  // Dollar PnL only — never W-L or graded-record profit.
  const pnl = c ? qualityNum(c.pnl) : null;
  const year = c ? qualityNum(c.yearlyPnl) : null;
  if (pnl != null && pnl < 0) return false;
  if (year != null && year < 0) return false;
  const month = c ? qualityNum(c.monthlyPnl) : null;
  const d30 = month != null ? month : (c ? qualityNum(c.tape30d) : null);
  if (d30 != null && d30 <= 0) return false;
  const last = (lastMap || capperLastTsMap(now))[(name || "").toLowerCase()];
  if (last != null && last < now - QUALITY_SEVEN_SECS) return false;
  return true;
}

const LAST20_MIN_WINS = 6;
const LAST20_MIN_N = 6;
const SPORT_MIN_N = 5;
const MIN_PAYOUT = 1.2;
function capperFormOk(name?: string): boolean {
  const r = last20Of(name || "");
  if (!r || !r.n) return true;
  return !(r.n >= LAST20_MIN_N && r.w < LAST20_MIN_WINS);
}
function capperSportOk(name: string | undefined, league?: string | null): boolean {
  const c = capperOf(name || "");
  const sports = c && c.sports;
  if (!sports || !Object.keys(sports).length) return true;
  const fam = sportFamilyOf(league);
  if (!fam) return true;
  const rec = sports[fam] || sports[(league || "")] || sports[(league || "").toUpperCase()] || (Object.keys(sports).map((k: string) => sports[k] && k.toLowerCase() === fam.toLowerCase() ? sports[k] : null).find(Boolean) as SportRec | undefined);
  if (!rec || !(rec.n >= SPORT_MIN_N)) return true;
  const profit = qualityNum(rec.profit);
  if (profit != null) return profit > 0;
  const roi = qualityNum(rec.roi);
  if (roi != null) return roi > 0;
  return (rec.w || 0) > (rec.l || 0);
}
function capperShownOk(name: string | undefined, now: number, lastMap?: Record<string, number>, league?: string | null): boolean {
  return capperQualityOk(name, now, lastMap) && capperFormOk(name) && capperSportOk(name, league);
}
function pickPayoutOk(p: { payout?: number | null; view?: { price?: number | null }; price?: number | null } | null | undefined): boolean {
  if (!p) return true;
  if (p.payout != null && p.payout > 0) return p.payout >= MIN_PAYOUT;
  const px = (p.view && p.view.price != null) ? p.view.price : (p.price != null ? p.price : null);
  if (px == null || !(px > 0 && px < 1)) return true;
  return (1 / px) >= MIN_PAYOUT;
}

function gradedWL(c?: Capper | null): { w: number; l: number; n: number; roi: number | null; profit: number | null; sample?: string } | null {
  const g = c && c.graded;
  if (!g || !(g.n > 0)) return null;
  return { w: g.w || 0, l: g.l || 0, n: g.n, roi: g.roi != null ? g.roi : null, profit: g.profit != null ? g.profit : null, sample: g.sample };
}
function recTone(w: number, l: number): { fg: string; bg: string } {
  if (!(w + l)) return { fg: "#334155", bg: "#F1F5F9" };
  return w > l ? { fg: GREEN, bg: "#DCFCE7" } : w < l ? { fg: RED, bg: "#FEE2E2" } : { fg: AMBER, bg: "#FEF3C7" };
}
function RecordPill(props: { w: number; l: number; roi?: number | null; label?: string }) {
  const n = props.w + props.l;
  const t = recTone(props.w, props.l);
  const text = n
    ? (wlText({ w: props.w, l: props.l }) + " · " + pctText(props.w / n) + (props.roi != null ? " · " + (props.roi >= 0 ? "+" : "") + Math.round(props.roi) + "% ROI" : "") + (props.label ? " · " + props.label : ""))
    : (props.label || "No sports W-L yet");
  return <span data-record-pill="1" style={{ display: "inline-block", padding: "0 8px", borderRadius: 999, background: t.bg, color: t.fg, border: "1.5px solid " + t.fg, fontWeight: 800, fontSize: 12, lineHeight: "20px", fontVariantNumeric: "tabular-nums" }}>{text}</span>;
}
function StatTile(props: { label: string; value: string; color?: string; bg?: string; sub?: string }) {
  return (
    <div style={{ flex: "1 1 72px", minWidth: 72, background: props.bg || "#F5F3FF", borderRadius: 14, padding: "10px 8px 9px", textAlign: "center", boxShadow: "0 1px 0 rgba(255,255,255,0.7) inset" }}>
      <div style={{ fontSize: 16, lineHeight: "20px", fontWeight: 850, color: props.color || NAVY, letterSpacing: "-0.02em", overflowWrap: "anywhere", fontVariantNumeric: "tabular-nums" }}>{props.value}</div>
      <div style={{ fontSize: 10, lineHeight: "13px", fontWeight: 750, color: "#64748B", marginTop: 3, letterSpacing: "0.05em", textTransform: "uppercase" }}>{props.label}</div>
      {props.sub ? <div style={{ fontSize: 10, lineHeight: "13px", fontWeight: 700, color: "#64748B", marginTop: 2 }}>{props.sub}</div> : null}
    </div>
  );
}
function WinRing(props: { pct: number; size?: number }) {
  const sz = props.size || 56;
  const r = sz / 2 - 5;
  const len = 2 * Math.PI * r;
  const color = props.pct >= 55 ? GREEN : props.pct >= 50 ? AMBER : RED;
  return (
    <div data-win-ring="1" style={{ position: "relative", width: sz, height: sz, flex: "none" }}>
      <svg width={sz} height={sz} viewBox={"0 0 " + sz + " " + sz}>
        <circle cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke="#DDD6FE" strokeWidth="6" />
        <circle cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeDasharray={((len * Math.max(0, Math.min(100, props.pct))) / 100) + " " + len} transform={"rotate(-90 " + (sz / 2) + " " + (sz / 2) + ")"} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: Math.round(sz * 0.28), fontWeight: 850, color: NAVY, lineHeight: 1, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>{Math.round(props.pct)}</div>
        <div style={{ fontSize: 8, marginTop: 2, fontWeight: 700, color: "#64748B", letterSpacing: "0.04em" }}>WIN %</div>
      </div>
    </div>
  );
}
function CapperShell(props: { live?: boolean; followed?: boolean; children: ReactNode }) {
  const accent = props.live ? "linear-gradient(90deg,#DC2626,#F97316)" : (props.followed ? "linear-gradient(90deg," + BLUE + "," + BLUE_BRIGHT + ")" : "linear-gradient(90deg," + BLUE + ",#A78BFA)");
  return (
    <div data-capper-shell={props.followed ? "followed" : "1"} style={{ borderRadius: 20, border: "1.5px solid #DDD6FE", background: "#FFFFFF", boxShadow: "0 6px 18px rgba(27,18,51,0.10)", overflow: "hidden", marginBottom: 14, fontFamily: "inherit" }}>
      <div style={{ height: 6, background: accent }} />
      <div style={{ padding: "12px 14px 14px" }}>{props.children}</div>
    </div>
  );
}
function isFollowedCapper(c: Capper): boolean {
  // Only the live pinned flag. Stale "My 40" / "Best Cappers" leftover after an unfollow must not count.
  return !!c.pinned;
}
function isLeaderboardCapper(c: Capper): boolean {
  if (c.onProfitBoard) return true;
  if (c.weeklyPnl != null || c.monthlyPnl != null || c.yearlyPnl != null) return true;
  return false;
}
function isLeaderboardEarner(c?: Capper | null): boolean {
  // Official all-time profit of $100k+ with no public graded W-L.
  if (!c || !isLeaderboardCapper(c) || c.pnl == null || c.pnl < 100000) return false;
  const g = c.graded;
  return !(g && g.n > 0);
}
function displayTier(tier: string): string {
  if (tier === "My 40" || tier === "Top 10" || tier === "Following" || tier === "Best Cappers") return "Best Cappers";
  return tier;
}
function tierColors(tier: string): { bg: string; fg: string } {
  if (tier === "My 40" || tier === "Top 10" || tier === "Following" || tier === "Best Cappers") return { bg: "#FEF3C7", fg: "#92400E" };
  if (tier === "Core") return { bg: BLUE_SOFT, fg: BLUE_INK };
  if (tier === "Top 50") return { bg: "#E0E7FF", fg: "#3730A3" };
  return { bg: "#F1F5F9", fg: "#334155" };
}
function TierChip(props: { tier: string }) {
  if (!props.tier) return null;
  const t = tierColors(props.tier);
  return <span data-tier={displayTier(props.tier)} style={{ display: "inline-block", padding: "0 8px", borderRadius: 999, background: t.bg, color: t.fg, border: "1.5px solid " + t.fg, fontSize: 11, fontWeight: 850, lineHeight: "18px" }}>{displayTier(props.tier)}</span>;
}
function RankChips(props: { ranks?: Record<string, number> }) {
  const r = props.ranks || {};
  const items: { k: string; n: number }[] = [];
  if (r.all_time) items.push({ k: "All-time", n: r.all_time });
  if (r.yearly) items.push({ k: "Year", n: r.yearly });
  if (r.monthly) items.push({ k: "Monthly", n: r.monthly });
  if (r.weekly) items.push({ k: "Weekly", n: r.weekly });
  if (!items.length) return null;
  return <>{items.map((x) => <Chip key={x.k} bg={BLUE} color="#FFFFFF">{x.k + " #" + x.n}</Chip>)}</>;
}
function CapperStatRow(props: { c: Capper }) {
  const g = gradedWL(props.c);
  const settled = !!(g && (g.w + g.l) > 0);
  const tone = settled ? recTone(g!.w, g!.l) : { fg: NAVY, bg: "#F5F3FF" };
  const tiles: ReactNode[] = [
    <StatTile key="rec" label="Record" value={settled ? (g!.w + "–" + g!.l) : "—"} color={tone.fg} bg={tone.bg} />,
    <StatTile key="wr" label="Win rate" value={settled ? pctText(g!.w / (g!.w + g!.l)) : "—"} color={tone.fg} bg={tone.bg} />,
  ];
  if (g && g.profit != null) tiles.push(<StatTile key="prof" label="Graded profit" value={(g.profit >= 0 ? "+" : "") + kMoney(g.profit)} color={g.profit >= 0 ? GREEN : RED} bg={g.profit >= 0 ? "#DCFCE7" : "#FEE2E2"} sub={g.roi != null ? ((g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI") : undefined} />);
  if (props.c.pnl != null) tiles.push(<StatTile key="pnl" label="All-time P&L" value={(props.c.pnl >= 0 ? "+" : "") + kMoney(props.c.pnl)} color={props.c.pnl >= 0 ? GREEN : RED} bg={props.c.pnl >= 0 ? "#DCFCE7" : "#FEE2E2"} sub={props.c.pnlSource === "kalshi_profile_metrics" ? "Kalshi profile" : (props.c.pnlSource === "sports_leaderboard_projected" ? "Sports board" : undefined)} />);
  if (props.c.yearlyPnl != null) tiles.push(<StatTile key="yr" label="Yearly P&L" value={(props.c.yearlyPnl >= 0 ? "+" : "") + kMoney(props.c.yearlyPnl)} color={props.c.yearlyPnl >= 0 ? GREEN : RED} sub="Sports board" />);
  if (props.c.monthlyPnl != null) tiles.push(<StatTile key="mo" label="Monthly P&L" value={(props.c.monthlyPnl >= 0 ? "+" : "") + kMoney(props.c.monthlyPnl)} color={props.c.monthlyPnl >= 0 ? GREEN : RED} sub="Sports board · no 30d" />);
  if (props.c.weeklyPnl != null) tiles.push(<StatTile key="wk" label="Weekly P&L" value={(props.c.weeklyPnl >= 0 ? "+" : "") + kMoney(props.c.weeklyPnl)} color={props.c.weeklyPnl >= 0 ? GREEN : RED} sub="Sports board" />);
  if (props.c.tape30d != null) tiles.push(<StatTile key="t30" label="Sports tape 30d" value={(props.c.tape30d >= 0 ? "+" : "") + kMoney(props.c.tape30d)} color={props.c.tape30d >= 0 ? GREEN : RED} sub="Settled public trades" />);
  if (props.c.tape7d != null) tiles.push(<StatTile key="t7" label="Sports tape 7d" value={(props.c.tape7d >= 0 ? "+" : "") + kMoney(props.c.tape7d)} color={props.c.tape7d >= 0 ? GREEN : RED} sub="Settled public trades" />);
  return (
    <div>
      <div data-record-strip="1" style={{ display: "flex", gap: 8, margin: "10px 0 0", flexWrap: "wrap" }}>{tiles}</div>
      <div style={{ fontSize: 11, fontWeight: 650, color: "#64748B", marginTop: 6, lineHeight: "15px" }}>All-time is official profile PnL; 7d/30d figures are from settled public sports trades.</div>
    </div>
  );
}
function sportsHeadline(c?: Capper | null): { text: string; color: string } {
  const g = gradedWL(c);
  if (g && (g.w + g.l) > 0) {
    const t = recTone(g.w, g.l);
    return { text: g.w + "–" + g.l + " · " + pctText(g.w / (g.w + g.l)) + (g.roi != null ? " · " + (g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI" : ""), color: t.fg };
  }
  if (isLeaderboardEarner(c)) return { text: "Leaderboard earner", color: GREEN };
  if (c && c.pnl != null) return { text: (c.pnl >= 0 ? "+" : "") + kMoney(c.pnl) + " all-time · no settled sports W-L yet", color: c.pnl >= 0 ? GREEN : RED };
  return { text: "No graded sports record yet", color: "#64748B" };
}
function BackerRow(props: { b: Backer; now: number }) {
  const b = props.b;
  const cap = capperOf(b.name);
  const fromBacker = b.rec && (b.rec.w + b.rec.l) > 0 ? { w: b.rec.w, l: b.rec.l, roi: (cap ? (cap.graded && cap.graded.roi != null ? cap.graded.roi : capperRoiPct(cap.nickname).roi) : null) as number | null } : null;
  const fromDb = gradedWL(cap);
  const g = fromBacker || (fromDb && (fromDb.w + fromDb.l) > 0 ? { w: fromDb.w, l: fromDb.l, roi: fromDb.roi } : null);
  return (
    <div data-backer-row={b.name} data-ucard-rec={b.name} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 8 }}>
      <Face name={b.name} size={28} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {g ? <RecordPill w={g.w} l={g.l} roi={g.roi} /> : (cap && isLeaderboardEarner(cap) ? <RecordPill w={0} l={0} label="Leaderboard earner" /> : <RecordPill w={0} l={0} />)}
          {b.tier ? <TierChip tier={b.tier} /> : null}
          {cap && cap.bestAt ? <Chip bg="#F5F3FF" color={BLUE_INK}>{"Best at " + cap.bestAt}</Chip> : null}
        </div>
        <div style={{ fontSize: 13, lineHeight: "18px", fontWeight: 750, color: NAVY, marginTop: 3, overflowWrap: "anywhere" }}>
          {b.name + " · " + money(b.cost) + (b.avg != null ? " at " + cents(b.avg) : "") + (b.lastTs ? " · bought " + ago(b.lastTs, props.now) : "")}
        </div>
        <Last20Dots name={b.name} />
        {b.lastSeen ? <div data-last-seen="1" style={{ marginTop: 4 }}><Chip bg="#FEF3C7" color={AMBER}>{"Last seen " + b.lastSeen}</Chip></div> : null}
      </div>
    </div>
  );
}
function openPicksFor(name: string, now: number): { p: Pick; game: Game }[] {
  const k = (name || "").toLowerCase();
  const out: { p: Pick; game: Game }[] = [];
  openGames(now).forEach((g: Game) => {
    (g.picks || []).forEach((p: Pick) => {
      if ((p.backers || []).some((b: Backer) => (b.name || "").toLowerCase() === k)) out.push({ p, game: g });
    });
  });
  return out;
}
function CapperPickMini(props: { p: Pick; game: Game; now: number; backerName?: string }) {
  const { p, game, now } = props;
  const mine = props.backerName ? p.backers.find((b: Backer) => (b.name || "").toLowerCase() === (props.backerName || "").toLowerCase()) : p.backers[0];
  const live = !!game.live || !!(p.startTs && p.startTs <= now);
  return (
    <div data-capper-pick={p.key} style={{ marginTop: 10, padding: "10px 0 0", borderTop: "1px solid #EDE9FE" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
        {game.league ? <Chip bg={BLUE_SOFT} color={BLUE_INK}>{game.league}</Chip> : null}
        <Chip bg="#F8FAFC" color="#334155">{(live ? "Started " : "Starts ") + (p.startTs || game.startTs ? ptTime(p.startTs || game.startTs) : "—")}</Chip>
        <AddedChip backers={mine ? [mine] : p.backers} now={now} />
        <PickFlags p={p} startTs={game.startTs} game={game} />
      </div>
      {isComboPick(p) ? (
        <ComboBlock legs={p.legs} now={now} ticker={p.ticker} comboUrl={p.comboUrl || (p.view && p.view.comboUrl)} yesNo={p.view.yesNo} price={p.view.price} payout={p.payout} stake={mine ? mine.cost : p.total} backers={mine ? [mine] : p.backers} copyPayload={comboLegsText({ backing: p.big, game: game.game, yesNo: (p.view && p.view.yesNo) || undefined, cost: mine ? mine.cost : p.total, price: p.view && p.view.price, comboUrl: p.comboUrl || (p.view && p.view.comboUrl), ticker: p.ticker, legs: p.legs })} />
      ) : (
        <>
      <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 850, color: NAVY, marginTop: 6, overflowWrap: "anywhere" }}>{p.big}{p.view.yesNo ? " · " + p.view.yesNo : ""}</div>
      <MatchupLine matchup={matchupOf(p.view.marketTitle, game.game, p.sub)} startTs={p.startTs || game.startTs} now={now} />
      {mine ? <div style={{ marginTop: 4, display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}><span style={{ fontSize: 20, lineHeight: "24px", fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{money(mine.cost)}</span><span style={{ fontSize: 13, fontWeight: 700, color: "#64748B" }}>{"on Kalshi" + (mine.avg != null ? " · entry " + cents(mine.avg) : "")}</span></div> : null}
      {mine && mine.lastSeen ? <div data-last-seen="1" style={{ marginTop: 6 }}><Chip bg="#FEF3C7" color={AMBER}>{"Last seen " + mine.lastSeen}</Chip></div> : null}
      <FreshPricePills p={p} now={now} />
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={p.view} /></div>
        </>
      )}
    </div>
  );
}
function FollowPickMini(props: { p: FollowPick; now: number }) {
  const p = props.p;
  const live = !!(p.startTs && p.startTs <= props.now);
  const view = { backing: p.backing || p.label || p.game, marketTitle: p.marketTitle || p.game, outcome: p.backing || p.label, yesNo: (p.yesNo === "No" ? "No" : "Yes") as "Yes" | "No", price: p.price ?? null, ticker: p.ticker };
  const fresh = (p.lastTs && props.now - (p.lastTs as number) <= FRESH_SECS && (p.cost || 0) >= FRESH_MIN) ? "fresh" : ((p.lastTs && props.now - (p.lastTs as number) > 24 * 3600) || !p.lastTs ? "hold" : null);
  const pill = (bg: string, fg: string, text: string, sub: string | null) => (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: 5, padding: "3px 10px", borderRadius: 999, background: bg, color: fg, border: "1.5px solid " + fg, fontSize: 13, fontWeight: 850 }}>{text}{sub ? <span style={{ fontSize: 11, fontWeight: 700, opacity: 0.85 }}>{sub}</span> : null}</span>
  );
  return (
    <div data-follow-pick={p.ticker} style={{ marginTop: 10, padding: "10px 0 0", borderTop: "1px solid #EDE9FE" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
        {p.league ? <Chip bg={BLUE_SOFT} color={BLUE_INK}>{p.league}</Chip> : null}
        {p.bt ? <Chip bg="#F8FAFC" color="#334155">{p.bt}</Chip> : null}
        {pickSourceLabel(p.source) ? <Chip bg="#EDE9FE" color="#5B21B6">{pickSourceLabel(p.source)}</Chip> : null}
        <Chip bg="#F8FAFC" color="#334155">{p.startTs ? ((live ? "Started " : "Starts ") + ptTime(p.startTs)) : "—"}</Chip>
        <AddedChip addedTs={p.addedTs} addedLastTs={p.addedLastTs} now={props.now} />
        <FollowFlags p={p} />
      </div>
      {isComboPick(p) ? (
        <ComboBlock legs={p.legs} now={props.now} ticker={p.ticker} comboUrl={p.comboUrl} yesNo={p.yesNo} price={p.price} payout={p.payout} stake={p.cost} backers={[{ name: p.nickname, cost: p.cost || 0, avg: p.entry ?? null, line: p.recordLine || p.nickname, tier: p.tier || "Best Cappers", pinned: true, lastTs: p.lastTs ?? null }]} copyPayload={comboLegsText(p)} />
      ) : (
        <>
      <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 850, color: NAVY, marginTop: 6, overflowWrap: "anywhere" }}>{(p.yesNo ? p.yesNo + " · " : "") + (p.contractTitle || p.backing || p.label || p.game)}</div>
      <MatchupLine matchup={matchupOf(p.marketTitle, p.game)} startTs={p.startTs} now={props.now} />
      <div style={{ marginTop: 4, display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        {p.cost != null && p.cost > 0 ? <span style={{ fontSize: 20, lineHeight: "24px", fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{kMoney(p.cost)}</span> : null}
        <span style={{ fontSize: 13, fontWeight: 700, color: "#64748B" }}>{"on Kalshi" + (p.price != null ? " · pays " + cents(p.price) : "") + (p.entry != null ? " · entry " + cents(p.entry) : "")}</span>
      </div>
      {fresh === "fresh" || fresh === "hold" || p.lastSeen ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
          {fresh === "fresh" ? pill("#DCFCE7", "#15803D", "Fresh", p.lastTs ? "bought " + ago(p.lastTs as number, props.now) : null) : null}
          {fresh === "hold" && !p.lastSeen ? pill("#F3F4F6", "#4B5563", "Hold", "no buys in 24h") : null}
          {p.lastSeen ? <Chip bg="#FEF3C7" color={AMBER}>{"Last seen " + p.lastSeen}</Chip> : null}
        </div>
      ) : null}
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={view} /></div>
        </>
      )}
    </div>
  );
}


function marketStatusOf(p: { status?: string; state?: string; result?: string | null }): { status: string; result: string } {
  return { status: String(p.status || p.state || "").toLowerCase(), result: String(p.result || "").toLowerCase() };
}
function midMarketPrice(price?: number | null, yesAsk?: number | null, noAsk?: number | null): boolean {
  const mid = (v?: number | null) => v != null && v > 1 - DECIDED_PX && v < DECIDED_PX;
  return mid(price) || mid(yesAsk) || mid(noAsk);
}
function decidedMarketPrice(price?: number | null, yesAsk?: number | null, noAsk?: number | null, bt?: string, yesNo?: string | null): boolean {
  if (yesAsk != null && yesAsk >= DECIDED_PX) return true;
  if (noAsk != null && noAsk >= DECIDED_PX) return true;
  if (price == null) return false;
  if (price >= DECIDED_PX || price <= 1 - DECIDED_PX) return true;
  return false;
}
// Hide a pick when its Kalshi market is closed/settled, the result is in, or the game has clearly finished.
// Still-active mid-price markets get a short grace window past typical duration so live OT stays visible.
function pickIsFinished(p: { status?: string; state?: string; result?: string | null; closeTs?: number; startTs?: number; yesAsk?: number | null; noAsk?: number | null; price?: number | null; view?: { price?: number | null; yesNo?: string | null }; bt?: string; league?: string }, now: number, league?: string, gameCloseTs?: number, gameStartTs?: number): boolean {
  const { status, result } = marketStatusOf(p);
  if (result === "yes" || result === "no" || KFINAL.indexOf(status) >= 0) return true;
  // inactive/closed/deactivated are not settled on their own — often used before tip or during a live halt.
  const close = p.closeTs || gameCloseTs || 0;
  if (close && now >= close) return true;
  const start = p.startTs || gameStartTs || 0;
  const px = (p.view && p.view.price != null) ? p.view.price : (p.price != null ? p.price : null);
  const started = !!(start && start <= now);
  if (started && decidedMarketPrice(px, p.yesAsk, p.noAsk) && !/^(UFC|MMA|BOXING)$/i.test(league || "")) return true;
  if (start && now >= start + liveSecsFor(league)) {
    const active = !status || status === "active" || status === "open" || status === "initialized" || status === "unopened";
    if (active && midMarketPrice(px, p.yesAsk, p.noAsk) && now < start + liveSecsFor(league) + FINISH_GRACE_SECS) return false;
    return true;
  }
  return false;
}
function comboHasFinishedLeg(p: { isCombo?: boolean; ticker?: string; legs?: ComboLeg[]; bt?: string; comboUrl?: string | null }, now: number, league?: string): boolean {
  if (!isComboPick(p)) return false;
  return (p.legs || []).some((leg: ComboLeg) => pickIsFinished({ startTs: leg.startTs, closeTs: leg.closeTs }, now, leg.league || league, leg.closeTs, leg.startTs));
}
function gamePickIsFinished(p: Pick, g: Game, now: number): boolean {
  if (comboHasFinishedLeg(p, now, g.league)) return true;
  return pickIsFinished(p, now, g.league, g.closeTs, g.startTs);
}
function followPickIsFinished(p: FollowPick, now: number): boolean {
  if (comboHasFinishedLeg(p, now, p.league)) return true;
  return pickIsFinished({ status: p.status, state: p.state, result: p.result, closeTs: p.closeTs, startTs: p.startTs, yesAsk: p.yesAsk, noAsk: p.noAsk, price: p.price, bt: p.bt }, now, p.league, undefined, p.startTs);
}
function gameOver(g: Game, now: number): boolean {
  const picks = g.picks || [];
  if (picks.length && picks.every((p: Pick) => gamePickIsFinished(p, g, now))) return true;
  if (!picks.length && pickIsFinished({ status: g.state, state: g.state, closeTs: g.closeTs, startTs: g.startTs }, now, g.league, g.closeTs, g.startTs)) return true;
  return false;
}
function ptDateParts(ts: number): { y: number; m: number; d: number; h: number; key: string } {
  const d = new Date((ts || 0) * 1000);
  const fallback = { y: 1970, m: 1, d: 1, h: 0, key: "1970-01-01" };
  if (isNaN(d.getTime())) return fallback;
  try {
    const parts: Record<string, string> = {};
    new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hour12: false }).formatToParts(d).forEach((p) => { if (p.type !== "literal") parts[p.type] = p.value; });
    let h = +parts.hour;
    if (h === 24) h = 0;
    if (!parts.year || !parts.month || !parts.day) return fallback;
    return { y: +parts.year, m: +parts.month, d: +parts.day, h: isNaN(h) ? 0 : h, key: parts.year + "-" + parts.month + "-" + parts.day };
  } catch (e) {
    return fallback;
  }
}
function ptDayOffset(startTs: number, now: number): number {
  const a = ptDateParts(startTs), b = ptDateParts(now);
  return Math.round((Date.UTC(a.y, a.m - 1, a.d) - Date.UTC(b.y, b.m - 1, b.d)) / 86400000);
}
// Client-side PT window: before 7pm, today's games (live included). From 7pm PT, today plus tomorrow.
function inSlateWindow(startTs: number, now: number, live?: boolean): boolean {
  if (live || (startTs > 0 && startTs <= now)) return true;
  if (!startTs) return false;
  const off = ptDayOffset(startTs, now);
  if (off === 0) return true;
  return off === 1 && ptDateParts(now).h >= 19;
}
function isRankedTodayGame(g: Game, now: number): boolean {
  if (gameOver(g, now)) return false;
  return inSlateWindow(g.startTs || 0, now, g.live);
}
function todayGames(games: Game[], now: number): Game[] {
  return games.filter((g: Game) => isRankedTodayGame(g, now));
}
function stakeOk(cost?: number | null, pick?: { isCombo?: boolean; ticker?: string; legs?: ComboLeg[]; bt?: string; comboUrl?: string | null } | null): boolean {
  const floor = isComboPick(pick || {}) ? MIN_STAKE_COMBO : MIN_STAKE;
  return (cost || 0) >= floor;
}
function filterMinStakeGames(games: Game[], now?: number): Game[] {
  const ts = now ?? Math.floor(Date.now() / 1000);
  const lastMap = capperLastTsMap(ts);
  return games.map((g: Game) => {
    const picks = (g.picks || []).map((p: Pick) => {
      const backers = (p.backers || []).filter((b: Backer) => stakeOk(b.cost, p) && capperShownOk(b.name, ts, lastMap, g.league));
      const total = Math.round(backers.reduce((sum: number, b: Backer) => sum + (b.cost || 0), 0) * 100) / 100;
      return { ...p, backers, total };
    }).filter((p: Pick) => p.backers.length && pickPayoutOk(p));
    return { ...g, picks };
  }).filter((g: Game) => (g.picks || []).length);
}
function isHiddenBook(c?: Capper | null): boolean {
  if (!c) return false;
  if (c.positionsVisible || c.postsVisible) return false;
  const src = (c.pickSource || "").toLowerCase();
  if (src.includes("post") || src.includes("position")) return false;
  const note = (c.rejectNote || "").toLowerCase();
  return note.includes("hidden");
}
function pickSourceLabel(src?: string | null): string {
  const s = (src || "").toLowerCase();
  if (s.includes("position") && s.includes("post")) return "Positions + posts";
  if (s.includes("post")) return "Profile posts";
  if (s.includes("position")) return "Open positions";
  return "";
}
function bookHiddenMessage(c?: Capper | FollowCapper | null): string {
  const posts = !!(c && ((c as FollowCapper).postsVisible || (c as Capper).postsVisible));
  const pos = !!(c && ((c as FollowCapper).positionsVisible || (c as Capper).positionsVisible));
  if (posts || pos) return "No open $1,000+ traditional-sports picks from this capper right now.";
  return "Positions are hidden and there are no public posts to copy.";
}
function mergeFollowPicks(games: Game[], now: number): Game[] {
  const byId: Record<string, Game> = {};
  const order: string[] = [];
  games.forEach((g: Game) => {
    byId[g.id] = { ...g, picks: (g.picks || []).map((p: Pick) => ({ ...p, backers: (p.backers || []).slice() })) };
    order.push(g.id);
  });
  const fps = ((DATA.following || {}).picks || []) as FollowPick[];
  fps.forEach((fp: FollowPick) => {
    if (followPickIsFinished(fp, now)) return;
    if (!stakeOk(fp.cost, fp) || !capperShownOk(fp.nickname, now, undefined, fp.league) || !pickPayoutOk(fp)) return;
    const start = fp.startTs || (fp.legs && fp.legs.reduce((m: number, l: ComboLeg) => (l.startTs && (!m || l.startTs < m) ? (l.startTs as number) : m), 0)) || fp.closeTs || 0;
    if (!start || start > now + 30 * 24 * 3600) return;
    const yesNo = (fp.yesNo === "No" ? "No" : "Yes") as "Yes" | "No";
    const key = (fp.ticker || "") + "|" + yesNo;
    const gid = fp.eventTicker || ((fp.game || "") + "|" + start);
    if (!byId[gid]) {
      byId[gid] = { id: gid, game: fp.game, league: fp.league || "Sports", startTs: start, start: "", live: !!(start && start <= now), state: start && start <= now ? "live" : "upcoming", picks: [] };
      order.push(gid);
    }
    const g = byId[gid];
    let pick = (g.picks || []).find((p: Pick) => p.key === key || (p.ticker === fp.ticker && p.view && p.view.yesNo === yesNo));
    const backer: Backer = { name: fp.nickname, cost: fp.cost || 0, avg: fp.entry ?? null, line: fp.recordLine || fp.nickname, tier: fp.tier || "Best Cappers", pinned: true, lastTs: fp.lastTs ?? null, lastSeen: fp.lastSeen, lastSeenTs: fp.lastSeenTs, addedTs: fp.addedTs ?? null, addedLastTs: fp.addedLastTs ?? null };
    if (!pick) {
      const total = backer.cost || 0;
      pick = { key, ticker: fp.ticker, eventTicker: fp.eventTicker, mid: fp.ticker, bt: fp.bt || "Other", big: fp.backing || fp.label || fp.game, sub: fp.marketTitle && fp.marketTitle !== (fp.backing || fp.label) ? fp.game : "", view: { backing: fp.backing || fp.label || fp.game, marketTitle: fp.marketTitle || fp.game, outcome: fp.backing || fp.label || "", yesNo, price: fp.price ?? null, ticker: fp.ticker, comboUrl: fp.comboUrl || null }, backers: [backer], total, tags: [backer.tier || "Best Cappers"], slip: fp.slip, startTs: start, state: fp.state || (start <= now ? "live" : "upcoming"), status: fp.status, result: fp.result ?? null, closeTs: fp.closeTs, yesAsk: fp.yesAsk, noAsk: fp.noAsk, isCombo: isComboPick(fp), legs: fp.legs, comboUrl: fp.comboUrl || null, payout: fp.payout ?? null };
      g.picks = (g.picks || []).concat([pick]);
    } else {
      // games[] combo cards are built without legs. Copy them from the follow pick
      // so Ranked/Coming Up never render "Combo · 0 legs" on a known KXMVE market.
      if (fp.legs && fp.legs.length && !(pick.legs && pick.legs.length)) pick.legs = fp.legs;
      if (fp.isCombo || isComboPick(fp) || (pick.legs && pick.legs.length >= 2)) pick.isCombo = true;
      if (fp.comboUrl && !pick.comboUrl) {
        pick.comboUrl = fp.comboUrl;
        if (pick.view) pick.view.comboUrl = fp.comboUrl;
      }
      if (fp.payout != null && pick.payout == null) pick.payout = fp.payout;
      if (fp.bt === "Combo" && pick.bt !== "Combo") pick.bt = "Combo";
      (pick.backers || []).forEach((b: Backer) => {
        if ((b.name || "").toLowerCase() !== (fp.nickname || "").toLowerCase()) return;
        if (fp.addedTs && (!b.addedTs || fp.addedTs < b.addedTs)) b.addedTs = fp.addedTs;
        if (fp.addedLastTs && (!b.addedLastTs || fp.addedLastTs > b.addedLastTs)) b.addedLastTs = fp.addedLastTs;
      });
      if (!(pick.backers || []).some((b: Backer) => (b.name || "").toLowerCase() === (fp.nickname || "").toLowerCase())) {
        pick.backers = (pick.backers || []).concat([backer]);
        pick.total = Math.round(pick.backers.reduce((sum: number, b: Backer) => sum + (b.cost || 0), 0) * 100) / 100;
        if (backer.tier && (pick.tags || []).indexOf(backer.tier) < 0) pick.tags = (pick.tags || []).concat([backer.tier]);
      }
    }
  });
  return order.map((id: string) => byId[id]).filter((g: Game) => (g.picks || []).length && !gameOver(g, now));
}
function openGames(now: number): Game[] {
  const horizon = now + 30 * 24 * 3600;
  const base = (DATA.games || []).map((g: Game) => ({ ...g, picks: (g.picks || []).filter((p: Pick) => hasMy40Backer(p) && !!(p.startTs || g.startTs) && (p.startTs || g.startTs) <= horizon && !gamePickIsFinished(p, g, now)) })).filter((g: Game) => g.picks.length && !gameOver(g, now));
  return filterMinStakeGames(mergeFollowPicks(base, now), now);
}
function uniqueSide(backers: Backer[]): { rec: WL; n: number } {
  const seen: Record<string, boolean> = {};
  let w = 0, l = 0, n = 0;
  backers.forEach((b: Backer) => {
    if (seen[b.name]) return;
    seen[b.name] = true;
    n += 1;
    if (b.rec) { w += b.rec.w; l += b.rec.l; }
  });
  return { rec: { w, l }, n };
}
// Ranked scoring, modeled on the whale scanner: Wilson lower bound + experience,
// per-sport records, thin-sample cap, heavy better-record opposition penalty,
// capper-count boost, official profit for leaderboard earners only (cannot outrank proven).
const PROVEN_MIN_N = 10;
const THIN_SCORE_CAP = 0.05;
const EARNER_SCORE_CAP = 0.05;
const NET_CLOSE = 10;
const NET_OPP_WR = 0.60;
function wilsonLower(w: number, n: number, z = 1.96): number {
  if (n <= 0) return 0;
  const z2 = z * z, p = w / n, denom = 1 + z2 / n;
  const center = p + z2 / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n);
  return (center - margin) / denom;
}
function sportFamilyOf(league?: string | null): string {
  const u = (league || "").toUpperCase();
  if (u === "CFB" || u === "NCAAF" || u === "NCAAFB") return "NCAAF";
  if (u === "CBB" || u === "NCAAB" || u === "NCAAMB") return "NCAAB";
  if (u === "ATP" || u === "WTA" || u === "ITF" || u === "TENNIS") return "Tennis";
  if (u === "UFC" || u === "MMA" || u === "BOXING") return "MMA";
  if (u === "EPL" || u === "UCL" || u === "UEL" || u === "MLS" || u === "LAL" || u === "SOCCER") return "Soccer";
  return league || "";
}
function capperOverall(c?: Capper | null): { w: number; l: number; n: number; pnl: number } {
  const g = c && c.graded;
  const w = (g && g.w) || 0, l = (g && g.l) || 0;
  const n = (g && g.n) || (w + l);
  const pnl = c && c.pnl != null ? c.pnl : 0;
  return { w, l, n, pnl };
}
function capperSportRec(c?: Capper | null, league?: string | null): SportRec | null {
  if (!c || !league) return null;
  const rec = (c.sports || {})[sportFamilyOf(league)];
  return rec && rec.n > 0 ? rec : null;
}
function isFollowedBacker(b: Backer): boolean {
  if (b.pinned || b.tier === "Best Cappers" || b.tier === "My 40" || b.tier === "Top 10" || b.tier === "Following") return true;
  const c = capperOf(b.name);
  return !!(c && isFollowedCapper(c));
}
function isThinCapper(c?: Capper | null, league?: string | null): boolean {
  return capperOverall(c).n < PROVEN_MIN_N;
}
function isProvenCapper(c?: Capper | null, league?: string | null): boolean {
  const ov = capperOverall(c);
  return !!c && ov.n >= PROVEN_MIN_N && ov.w > ov.l;
}
function capperRankScore(c?: Capper | null, league?: string | null): number {
  if (!c) return 0;
  const ov = capperOverall(c);
  if (ov.n <= 0) {
    // Leaderboard earner: official profit only, capped so it cannot outrank a proven record.
    if (isLeaderboardEarner(c) || (isLeaderboardCapper(c) && ov.pnl >= 100000)) {
      return Math.min(EARNER_SCORE_CAP, Math.log10(1 + Math.max(0, ov.pnl) / 100000) / 6);
    }
    return 0;
  }
  const oRate = wilsonLower(ov.w, ov.n);
  let sRate = oRate, sN = 0;
  const sr = capperSportRec(c, league);
  if (sr && sr.n > 0) { sRate = wilsonLower(sr.w, sr.n); sN = sr.n; }
  const sportW = sN / (sN + 8);
  const rate = sportW * sRate + (1 - sportW) * oRate;
  const thin = isThinCapper(c, league);
  const expF = ov.n / (ov.n + 40);
  const volF = thin ? 0 : Math.min(1, Math.log(1 + Math.max(0, ov.pnl)) / Math.log(10) / 5);
  const conf = thin ? 0.50 * expF : (0.75 * expF + 0.25 * volF);
  const score = rate * (thin ? 0.15 * conf : (0.30 + 0.70 * conf));
  return thin ? Math.min(score, THIN_SCORE_CAP) : score;
}
function recForCapper(c?: Capper | null, league?: string | null, fallback?: WL | null): WL | null {
  const sr = capperSportRec(c, league);
  if (sr && sr.n >= 5) return { w: sr.w, l: sr.l, n: sr.n };
  const ov = capperOverall(c);
  if (ov.n > 0) return { w: ov.w, l: ov.l, n: ov.n };
  return fallback && (fallback.w + fallback.l) > 0 ? fallback : null;
}
function pickPrice(p: Pick): number | null {
  return p.view && p.view.price != null && p.view.price > 0 ? p.view.price : null;
}
function isPaddedPrice(p: Pick): boolean {
  const px = pickPrice(p);
  return px != null && px >= 0.90;
}
function isLongshotPrice(p: Pick): boolean {
  const px = pickPrice(p);
  return px != null && px < 0.40;
}
const netPts = (net: number): number => Math.round(net);
const netText = (net: number): string => "Net " + (net > 0 ? "+" + net : String(net));
function oppositionPicks(p: Pick, game: Game): Pick[] {
  const out: Pick[] = [];
  const seen: Record<string, boolean> = {};
  (game.picks || []).forEach((q: Pick) => {
    if (q.key === p.key || seen[q.key]) return;
    const sameMkt = !!(p.mid && q.mid && q.mid === p.mid && q.view.yesNo && p.view.yesNo && q.view.yesNo !== p.view.yesNo);
    const otherTeamML = p.bt === "Moneyline" && q.bt === "Moneyline" && !!p.mid && !!q.mid && q.mid !== p.mid && !!q.view.yesNo && !!p.view.yesNo && q.view.yesNo === p.view.yesNo;
    if (sameMkt || otherTeamML) { seen[q.key] = true; out.push(q); }
  });
  return out;
}
function oppositeOf(p: Pick, game: Game): Pick[] {
  return oppositionPicks(p, game);
}
interface NetInfo { net: number; raw: number; own: number; opp: number; ownRec: WL; oppRec: WL; ownN: number; oppN: number; my40: number; contested: boolean; proven: boolean; padded: boolean; longshot: boolean; tier: number; bestN: number; dbRank: number }
function recOfBackers(backers: Backer[], league?: string | null): { rec: WL; n: number; score: number; proven: boolean; earner: boolean; my40: number; bestN: number } {
  const seen: Record<string, boolean> = {};
  let w = 0, l = 0, n = 0, score = 0, my40 = 0, proven = false, earner = false, bestN = 0;
  backers.forEach((b: Backer) => {
    if (seen[b.name]) return;
    seen[b.name] = true;
    n += 1;
    const c = capperOf(b.name);
    const r = recForCapper(c, league, b.sportRec || b.rec || null);
    if (r) { w += r.w; l += r.l; }
    score += capperRankScore(c, league);
    const ov = capperOverall(c);
    if (ov.n > bestN) bestN = ov.n;
    if (isFollowedBacker(b)) my40 += 1;
    if (isProvenCapper(c, league)) proven = true;
    if (isLeaderboardEarner(c)) earner = true;
  });
  return { rec: { w, l }, n, score, proven, earner, my40, bestN };
}
function netOf(p: Pick, game: Game): NetInfo {
  const oppPicks = oppositionPicks(p, game);
  const oppW: Record<string, boolean> = {};
  oppPicks.forEach((q: Pick) => q.backers.forEach((b: Backer) => { oppW[b.name] = true; }));
  const mineW: Record<string, boolean> = {};
  p.backers.forEach((b: Backer) => { mineW[b.name] = true; });
  const lg = game.league;
  // Score from every tracked backer (hedges dropped). Followed Best Cappers add a count boost.
  const ownAll = p.backers.filter((b: Backer) => !oppW[b.name]);
  const own = recOfBackers(ownAll, lg);
  const oppB: Backer[] = [];
  const seen: Record<string, boolean> = {};
  oppPicks.forEach((q: Pick) => q.backers.forEach((b: Backer) => { if (seen[b.name] || mineW[b.name]) return; seen[b.name] = true; oppB.push(b); }));
  const opp = recOfBackers(oppB, lg);
  const ownScore = own.score;
  // Veteran (best capper 10+ settled) > leaderboard earner > thin sample.
  // Price, stake, and capper-count cannot lift a thin side above those tiers.
  const tier = own.proven ? 2 : (own.earner ? 1 : 0);
  let raw = 100 * (ownScore - opp.score);
  if (tier >= 1 && own.my40) raw += Math.min(16, own.my40 * 6);
  const stake = ownAll.reduce((a: number, b: Backer) => a + (b.cost || 0), 0);
  if (own.proven && stake > 0) raw += Math.min(8, Math.log10(1 + stake) * 3);
  const px = pickPrice(p);
  const padded = isPaddedPrice(p);
  const comboBoost = !!comboBoostBacker(p);
  const longshot = isLongshotPrice(p) && !comboBoost;
  if (comboBoost) raw += 15;
  if (padded) raw -= 80;
  else if (longshot) raw -= 40;
  else if (tier >= 1 && px != null && px >= 0.55 && px <= 0.82) raw += 8;
  if (opp.proven && opp.score > ownScore + 1e-6) raw -= 100;
  if (!own.proven && opp.proven) raw -= 50;
  const net = Math.round(raw);
  const oppNBets = opp.rec.w + opp.rec.l;
  const contested = oppNBets >= ELITE_MIN_BETS && (wlRate(opp.rec) >= NET_OPP_WR || net < NET_CLOSE || (opp.proven && opp.score > ownScore + 1e-6));
  return { net, raw, own: ownScore, opp: opp.score, ownRec: own.rec, oppRec: opp.rec, ownN: own.n, oppN: opp.n, my40: own.my40, contested, proven: own.proven, padded, longshot, tier, bestN: own.bestN, dbRank: bestDbRank(ownAll) };
}
function hasMy40Backer(p: Pick): boolean {
  return (p.backers || []).some(isFollowedBacker);
}
function weakerSide(p: Pick, game: Game): boolean {
  const mine = netOf(p, game).net;
  return oppositionPicks(p, game).some((q: Pick) => netOf(q, game).net > mine + 1e-12);
}
function rankCmpNet(a: NetInfo, b: NetInfo): number {
  // Experience first: veterans, then big leaderboard earners, then thin samples.
  // Within a tier, longshots and 90c+ padding sort down; then net, then sample size.
  // Best Cappers database rank (1 = best) surfaces those $1,000+ picks first, after tier and price-quality.
  return (b.tier - a.tier) || (Number(a.longshot) - Number(b.longshot)) || (Number(a.padded) - Number(b.padded)) || ((a.dbRank || 9999) - (b.dbRank || 9999)) || (b.net - a.net) || (b.bestN - a.bestN) || (b.raw - a.raw) || (b.my40 - a.my40);
}
function bestPickFirst(picks: Pick[], game: Game): Pick[] {
  return picks.slice().sort((a: Pick, b: Pick) => rankCmpNet(netOf(a, game), netOf(b, game)) || ((b.total || 0) - (a.total || 0)));
}
function pickRankWhy(p: Pick, game: Game, n: NetInfo): string {
  const lg = sportFamilyOf(game.league);
  const names = (p.backers || []).filter(isFollowedBacker).map((b: Backer) => {
    const c = capperOf(b.name);
    const r = recForCapper(c, game.league, b.sportRec || b.rec || null);
    const rec = r && (r.w + r.l) ? wlText(r) : (c && isLeaderboardEarner(c) ? "earner" : "n/a");
    return b.name + " " + rec;
  }).slice(0, 2).join(", ");
  const bits = [names || (n.tier === 2 ? "veteran" : n.tier === 1 ? "earner" : "thin")];
  if (n.tier === 2) bits.push("veteran");
  else if (n.tier === 1) bits.push("earner");
  else bits.push("new");
  if (n.ownRec.w + n.ownRec.l) bits.push(wlText(n.ownRec) + (lg ? " " + lg : ""));
  if (n.my40 > 1) bits.push(n.my40 + " followed");
  if (n.contested) bits.push("contested " + wlText(n.oppRec));
  if (n.longshot) bits.push("longshot");
  if (n.padded) bits.push("90c+");
  const px = pickPrice(p);
  if (px != null && !n.padded) bits.push(cents(px));
  bits.push(netText(n.net));
  return bits.join(" · ");
}
function pickRec(p: Pick): WL {
  return uniqueSide(p.backers).rec;
}
function allPicks(games: Game[]): { p: Pick; game: Game }[] {
  const out: { p: Pick; game: Game }[] = [];
  games.forEach((g: Game) => g.picks.forEach((p: Pick) => out.push({ p, game: g })));
  return out;
}
function sideCompare(p: Pick, game: Game): SideCmp | null {
  const opp = oppositeOf(p, game);
  if (!opp.length) return null;
  const mine: { r: WL; name: string; sc: number }[] = [];
  const theirs: { r: WL; name: string; sc: number }[] = [];
  const seen: Record<string, boolean> = {};
  p.backers.forEach((b: Backer) => {
    const c = capperOf(b.name);
    const r = recForCapper(c, game.league, b.sportRec || b.rec || null);
    if (r) mine.push({ r, name: b.name, sc: capperRankScore(c, game.league) });
  });
  opp.forEach((q: Pick) => q.backers.forEach((b: Backer) => {
    if (seen[b.name]) return;
    seen[b.name] = true;
    const c = capperOf(b.name);
    const r = recForCapper(c, game.league, b.sportRec || b.rec || null);
    if (r) theirs.push({ r, name: b.name, sc: capperRankScore(c, game.league) });
  }));
  if (!mine.length || !theirs.length) return null;
  const best = (list: { r: WL; name: string; sc: number }[]) => list.slice().sort((x, y) => (y.sc - x.sc) || (wlBetter(x.r, y.r) ? -1 : wlBetter(y.r, x.r) ? 1 : 0))[0];
  const tb = best(mine), ob = best(theirs);
  const verdict = ob.sc - tb.sc > 1e-6 ? "other" : tb.sc - ob.sc > 1e-6 ? "this" : null;
  return { verdict, thisBest: tb.r, oppBest: ob.r, thisName: tb.name, oppName: ob.name };
}
function freshOf(p: Pick, now: number): { tag: "fresh" | "hold" | null; ts: number | null } {
  const ts = Math.max(0, ...p.backers.map((b: Backer) => b.lastTs || 0));
  if (ts && now - ts <= FRESH_SECS && p.total >= FRESH_MIN) return { tag: "fresh", ts };
  if (p.backers.every((b: Backer) => !b.lastTs || now - (b.lastTs as number) > 24 * 3600)) return { tag: "hold", ts: null };
  return { tag: null, ts: null };
}
function slipTierOf(p: Pick): "good" | "slight" | "much" | null {
  if (p.slip == null) return null;
  if (p.slip <= 2) return "good";
  if (p.slip <= 5) return "slight";
  return "much";
}

function KalshiBuyButton(props: { view: KalshiView }) {
  const v = props.view;
  const ok = !!v.yesNo && v.price != null;
  const yes = v.yesNo === "Yes";
  return (
    <div data-k-yesno="1" data-k-side={ok ? v.yesNo : undefined} style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "100%", boxSizing: "border-box", padding: "12px 14px", borderRadius: 14, background: ok ? (yes ? GREEN : RED) : "#94A3B8", color: "#FFFFFF", fontSize: 18, fontWeight: 900 }}>
      <span data-k-price="1">{ok ? (v.yesNo + " · pays " + cents(v.price)) : "No Kalshi line"}</span>
    </div>
  );
}
function OnKalshiBox(props: { view: KalshiView }) {
  const v = props.view;
  if (!v.yesNo || !v.marketTitle) return null;
  const yes = v.yesNo === "Yes";
  const plain = !v.outcome || /^(yes|no)$/i.test(v.outcome) || (v.marketTitle.toLowerCase().indexOf((v.outcome || "").toLowerCase()) >= 0 && /^(will|who|what|which|is|are|does|do)\b/i.test(v.marketTitle));
  const url = kalshiUrlOf(v.ticker, v.comboUrl);
  const col = yes ? GREEN : RED;
  return (
    <div data-on-kalshi="1" style={{ marginTop: 10, padding: "10px 12px", borderRadius: 14, border: "1.5px dashed " + BLUE, background: "#F5F3FF" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 850, letterSpacing: "0.08em", textTransform: "uppercase", color: BLUE }}>On Kalshi</span>
        {url ? <a data-kalshi-link="1" href={url} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 800, color: BLUE, textDecoration: "none" }}>Open on Kalshi ↗</a> : null}
      </div>
      <div data-ok-title="1" style={{ fontSize: 15, lineHeight: "20px", fontWeight: 750, color: NAVY, marginTop: 4, overflowWrap: "anywhere" }}>{v.marketTitle}</div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 6, fontSize: 15, fontWeight: 700, color: "#475569" }}>
        {plain ? <span>{"Tap"}</span> : <><span>{"Tap"}</span><b data-ok-option="1" style={{ color: NAVY, overflowWrap: "anywhere" }}>{"“" + v.outcome + "”"}</b><span>{"→"}</span></>}
        <span data-ok-side="1" style={{ display: "inline-block", padding: "1px 12px", borderRadius: 999, background: col, color: "#FFFFFF", fontWeight: 850, fontSize: 15 }}>{v.yesNo}</span>
      </div>
    </div>
  );
}
function OtherSide(props: { p: Pick; opp: Pick[] }) {
  const p = props.p;
  if (!props.opp.length) {
    return <div data-other-side="1" style={{ marginTop: 10, padding: "9px 12px", borderRadius: 14, background: "#F5F3FF", color: BLUE_INK }}><div style={{ fontSize: 11, fontWeight: 850, letterSpacing: "0.08em", textTransform: "uppercase", color: BLUE }}>Other side</div><div style={{ fontSize: 14, fontWeight: 700, marginTop: 2 }}>No tracked cappers on the other side</div></div>;
  }
  const backers: (Backer & { pickBig: string })[] = [];
  props.opp.forEach((q: Pick) => q.backers.forEach((b: Backer) => backers.push({ ...b, pickBig: q.big })));
  const tot = props.opp.reduce((a: number, q: Pick) => a + q.total, 0);
  return (
    <div data-other-side="1" style={{ marginTop: 10, padding: "10px 12px", borderRadius: 14, border: "1.5px solid #FCD34D", background: "#FFFBEB" }}>
      <div style={{ fontSize: 11, fontWeight: 850, letterSpacing: "0.08em", textTransform: "uppercase", color: AMBER }}>Other side</div>
      <div style={{ fontSize: 15, fontWeight: 850, color: NAVY, marginTop: 2 }}>
        <span style={{ color: GREEN }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s") + " · " + kMoney(p.total)}</span>
        {" vs "}
        <span>{backers.length + " capper" + (backers.length === 1 ? "" : "s") + " · " + kMoney(tot)}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#57534E", marginTop: 2 }}>{"They bet: " + props.opp.map((q: Pick) => q.big).join(", ")}</div>
      {backers.map((b, i) => (
        <div key={b.name + i} style={{ display: "flex", justifyContent: "space-between", gap: 8, borderTop: i ? undefined : "1px solid #FDE68A", marginTop: i ? 2 : 6, paddingTop: i ? 0 : 6, fontSize: 13, fontWeight: 650, color: "#57534E" }}>
          <span style={{ overflowWrap: "anywhere" }}>{b.line}</span>
          <span style={{ fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{money(b.cost)}</span>
        </div>
      ))}
    </div>
  );
}
function RecordFlag(props: { cmp: SideCmp }) {
  const c = props.cmp;
  if (c.verdict !== "other") return null;
  return <div data-record-flag={c.verdict} style={{ marginTop: 8 }}><Chip bg="#FEF3C7" color={AMBER}>{"Opp " + c.oppName + " " + wlText(c.oppBest)}</Chip></div>;
}
function FreshPricePills(props: { p: Pick; now: number }) {
  const fresh = freshOf(props.p, props.now);
  if (fresh.tag !== "fresh") return null;
  return (
    <div data-pills="1" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
      <Chip bg="#DCFCE7" color={GREEN}>{"Fresh" + (fresh.ts ? " " + ago(fresh.ts, props.now) : "")}</Chip>
    </div>
  );
}
function PickRankChips(props: { p: Pick; game: Game; now: number }) {
  const n = netOf(props.p, props.game);
  const fresh = freshOf(props.p, props.now);
  const cmp = sideCompare(props.p, props.game);
  const chips: ReactNode[] = [];
  if (n.contested) chips.push(<Chip key="c" bg="#FFEDD5" color="#9A3412">{"Contested · " + wlText(n.oppRec)}</Chip>);
  if (n.tier === 2) chips.push(<Chip key="v" bg="#DCFCE7" color={GREEN}>Veteran</Chip>);
  else if (n.tier === 1) chips.push(<Chip key="e" bg="#DCFCE7" color={GREEN}>Leaderboard earner</Chip>);
  else chips.push(<Chip key="t" bg="#FEF3C7" color={AMBER}>New</Chip>);
  if (n.longshot) chips.push(<Chip key="ls" bg="#F1F5F9" color="#475569">Longshot</Chip>);
  if (n.padded) chips.push(<Chip key="p" bg="#F1F5F9" color="#475569">90c+</Chip>);
  if (fresh.tag === "fresh") chips.push(<Chip key="f" bg="#DCFCE7" color={GREEN}>Fresh</Chip>);
  if (cmp && cmp.verdict === "other") chips.push(<Chip key="o" bg="#FEF3C7" color={AMBER}>{"Opp " + cmp.oppName + " " + wlText(cmp.oppBest)}</Chip>);
  if (!chips.length) return null;
  return <div data-rank-chips="1" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>{chips}</div>;
}
function MoreBetsRow(props: { n: number; open: boolean; onToggle: () => void; noun?: string }) {
  if (props.n <= 0) return null;
  return (
    <button type="button" data-more-bets="1" aria-expanded={props.open} onClick={props.onToggle} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", marginTop: 8, padding: "8px 12px", borderRadius: 12, border: "0", background: BLUE_SOFT, color: BLUE_INK, fontWeight: 800, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
      <span>{(props.open ? "▴ Hide " : "▾ ") + props.n + " more bet" + (props.n === 1 ? "" : "s") + (props.open ? "" : " on this " + (props.noun || "game"))}</span>
      <span style={{ fontSize: 12, fontWeight: 700, color: "#64748B" }}>{props.open ? "Collapse" : "Tap to expand"}</span>
    </button>
  );
}

function tapeStake(p: Pick): string {
  const costs = (p.backers || []).map((b: Backer) => b.cost || 0).filter((x: number) => x > 0);
  if (!costs.length) return p.total ? money(p.total) : "—";
  const lo = Math.min.apply(null, costs), hi = Math.max.apply(null, costs);
  if (hi - lo < 0.005) return money(lo);
  return money(lo) + "–" + money(hi);
}

function UCard(props: { p: Pick; game: Game; now: number; stake: string; moreRow?: ReactNode; stakeLine?: string; rankNo?: number }) {
  const p = props.p;
  const v = p.view;
  const opp = oppositeOf(p, props.game);
  const cmp = sideCompare(p, props.game);
  const net = netOf(p, props.game);
  const top = p.backers.slice(0, 3);
  const rest = p.backers.slice(3);
  const colorOf = (x: string): string[] => (({ "Best Cappers": ["#FEF3C7", "#92400E"], "My 40": ["#FEF3C7", "#92400E"], "Top 10": ["#FEF3C7", "#92400E"], Following: ["#FEF3C7", "#92400E"], Core: ["#EDE9FE", "#5B21B6"], "Top 50": ["#E0E7FF", "#3730A3"], Board: ["#F1F5F9", "#334155"], Weekly: ["#F1F5F9", "#334155"] } as Record<string, string[]>)[x] || ["#F1F5F9", "#334155"]);
  return (
    <div data-ucard={p.key} data-contested={net.contested ? "1" : "0"} style={{ borderRadius: 18, border: net.contested ? "2px solid #F59E0B" : "1.5px solid #DDD6FE", background: "#FFFFFF", boxShadow: "0 4px 14px rgba(27,18,51,0.08)", overflow: "hidden", marginBottom: 10, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
      <div style={{ padding: "12px 14px 12px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 6 }}>
          {props.rankNo ? <span data-card-no="1" style={{ display: "inline-block", minWidth: 26, textAlign: "center", padding: "2px 8px", borderRadius: 999, background: BLUE, color: "#FFFFFF", fontSize: 13, fontWeight: 900 }}>{"#" + props.rankNo}</span> : null}
          {props.game.live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
          <span style={{ fontSize: 12, fontWeight: 700, color: "#64748B" }}>{props.game.league + " · " + (props.game.startTs ? ptTime(props.game.startTs) : "") + (p.bt ? " · " + p.bt : "")}</span>
          <AddedChip backers={p.backers} now={props.now} />
          <ColdChip p={p} />
          <PickFlags p={p} startTs={props.game.startTs} game={props.game} />
        </div>
        {isComboPick(p) ? (
          <ComboBlock legs={p.legs} now={props.now} ticker={p.ticker} comboUrl={p.comboUrl || v.comboUrl} yesNo={v.yesNo} price={v.price} payout={p.payout} stake={p.total} backers={p.backers} copyPayload={comboLegsText({ backing: p.big, game: props.game.game, yesNo: v.yesNo || undefined, cost: p.total, price: v.price, comboUrl: p.comboUrl || v.comboUrl, ticker: p.ticker, legs: p.legs })} />
        ) : (
          <>
        <div data-ucard-big="1" style={{ fontSize: 22, lineHeight: "27px", fontWeight: 850, letterSpacing: "-0.01em", overflowWrap: "anywhere", color: NAVY }}>{p.big}{v.yesNo ? " · " + v.yesNo : ""}</div>
        <MatchupLine matchup={matchupOf(v.marketTitle, p.sub, props.game.game)} startTs={p.startTs || props.game.startTs} now={props.now} />
        <div data-ucard-sum="1" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 10 }}>
          <span data-ucard-total="1" style={{ display: "inline-block", padding: "3px 12px", borderRadius: 12, background: BLUE_BRIGHT, color: "#FFFFFF", fontSize: 28, lineHeight: "34px", fontWeight: 900, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>{kMoney(p.total)}</span>
          <span data-ucard-count="1" style={{ display: "inline-block", padding: "4px 10px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 15, fontWeight: 850 }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s")}</span>
          <span data-net-pill="1" style={{ display: "inline-block", padding: "3px 9px", borderRadius: 999, background: "#F8FAFC", color: "#334155", border: "1px solid #CBD5E1", fontSize: 13, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{netText(net.net)}</span>
          {p.tags.map((x: string) => <span key={x} style={{ display: "inline-block", padding: "3px 9px", borderRadius: 999, background: colorOf(x)[0], color: colorOf(x)[1], fontSize: 13, fontWeight: 850, border: "1.5px solid " + colorOf(x)[1] }}>{x}</span>)}
        </div>
        <PickRankChips p={p} game={props.game} now={props.now} />
        {props.moreRow}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
          <div style={{ flex: 1 }}><KalshiBuyButton view={v} /></div>
          <div data-k-stake="1" style={{ fontSize: 14, fontWeight: 800, color: GREEN, lineHeight: "17px" }}>{"Stake"}<br />{(props.stakeLine ? props.stake : (props.stake && props.stake !== "$2–4" ? props.stake : tapeStake(p)))}</div>
        </div>
        {props.stakeLine ? <div data-stake-line="1" style={{ marginTop: 6, fontSize: 14, fontWeight: 850, color: GREEN, fontVariantNumeric: "tabular-nums" }}>{props.stakeLine}</div> : null}
        <OnKalshiBox view={v} />
        {top.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
        <OtherSide p={p} opp={opp} />
        {rest.length ? (
          <details data-ucard-more="1" style={{ marginTop: 8 }}>
            <summary style={{ cursor: "pointer", fontWeight: 800, fontSize: 14, color: BLUE }}>{"Details · +" + rest.length + " more"}</summary>
            {rest.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
          </details>
        ) : null}
          </>
        )}
      </div>
    </div>
  );
}
function AltBet(props: { p: Pick; game: Game; now: number }) {
  const p = props.p;
  const opp = oppositeOf(p, props.game);
  const cmp = sideCompare(p, props.game);
  const net = netOf(p, props.game);
  return (
    <div data-alt-bet={p.key} data-contested={net.contested ? "1" : "0"} style={{ borderRadius: 14, border: net.contested ? "2px solid #F59E0B" : "1.5px solid #DDD6FE", background: "#FFFFFF", padding: "10px 12px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 18, lineHeight: "22px", fontWeight: 850, overflowWrap: "anywhere", flex: 1, minWidth: 0, color: NAVY }}>{p.big}{p.view.yesNo ? " · " + p.view.yesNo : ""}</div>
        <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 10, background: BLUE_BRIGHT, color: "#FFFFFF", fontSize: 18, fontWeight: 900, fontVariantNumeric: "tabular-nums" }}>{kMoney(p.total)}</span>
      </div>
      <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}><AddedChip backers={p.backers} now={props.now} /><PickFlags p={p} startTs={props.game.startTs} game={props.game} /></div>
      <MatchupLine matchup={matchupOf(p.view.marketTitle, p.sub, props.game.game)} startTs={p.startTs || props.game.startTs} now={props.now} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 6 }}>
        <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 13, fontWeight: 850 }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s")}</span>
        <span data-net-pill="1" style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: "#F8FAFC", color: "#334155", border: "1px solid #CBD5E1", fontSize: 12, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{netText(net.net)}</span>
        {p.tags.map((x: string) => <span key={x} style={{ display: "inline-block", padding: "1px 8px", borderRadius: 999, background: "#F1F5F9", color: "#334155", fontSize: 12, fontWeight: 800, border: "1px solid #94A3B8" }}>{x}</span>)}
      </div>
      {isComboPick(p) ? (
        <ComboBlock legs={p.legs} now={props.now} ticker={p.ticker} comboUrl={p.comboUrl || p.view.comboUrl} yesNo={p.view.yesNo} price={p.view.price} payout={p.payout} stake={p.total} backers={p.backers} copyPayload={comboLegsText({ backing: p.big, game: props.game.game, yesNo: p.view.yesNo || undefined, cost: p.total, price: p.view.price, comboUrl: p.comboUrl || p.view.comboUrl, ticker: p.ticker, legs: p.legs })} />
      ) : (
        <>
      <PickRankChips p={p} game={props.game} now={props.now} />
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={p.view} /></div>
      <OnKalshiBox view={p.view} />
      {p.backers.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
        </>
      )}
    </div>
  );
}
function GameHeader(props: { g: Game; now: number; rankNo?: number; rec?: WL; cappers?: number }) {
  const g = props.g;
  if (!g.startTs) return null;
  return (
    <div data-game-start="1" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "14px 2px 6px", fontSize: 16, fontWeight: 850, color: BLUE_INK }}>
      {props.rankNo ? <span data-game-rank="1" style={{ display: "inline-block", minWidth: 30, textAlign: "center", padding: "2px 9px", borderRadius: 999, background: BLUE, color: "#FFFFFF", fontSize: 14, fontWeight: 900 }}>{"#" + props.rankNo}</span> : null}
      {g.live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
      <span data-game-start-time="1">{(g.live ? "Started " : "Starts ") + ptTime(g.startTs)}</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: "#475569" }}>{(g.live ? ago(g.startTs, props.now) : "in " + untilText(g.startTs, props.now)) + " · " + g.league}</span>
      {props.rec ? <span data-game-rec="1" style={{ display: "inline-block", padding: "2px 10px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 13, fontWeight: 850, border: "1.5px solid " + BLUE }}>{(props.rec.w + props.rec.l ? wlText(props.rec) + " · " + pctText(wlRate(props.rec)) : "No graded record") + (props.cappers ? " · " + props.cappers + " capper" + (props.cappers === 1 ? "" : "s") : "")}</span> : null}
    </div>
  );
}
function GameBlock(props: { g: Game; now: number; stake: string; showStart?: boolean; rankNo?: number; rec?: WL; cappers?: number; stakeLine?: string }) {
  const [open, setOpen] = useState(false);
  const picks = bestPickFirst(props.g.picks, props.g);
  const main = picks[0];
  const rest = picks.slice(1);
  const groups = BT_ORDER.map((bt: string) => ({ bt, picks: rest.filter((q: Pick) => (q.bt || "Other") === bt) })).filter((x) => x.picks.length);
  if (!main) return null;
  return (
    <div data-game-block={props.g.id}>
      {props.showStart || props.rankNo ? <GameHeader g={props.g} now={props.now} rankNo={props.rankNo} rec={props.rec} cappers={props.cappers} /> : null}
      <UCard p={main} game={props.g} now={props.now} stake={props.stake} moreRow={rest.length ? <MoreBetsRow noun="game" n={rest.length} open={open} onToggle={() => setOpen(!open)} /> : undefined} stakeLine={props.stakeLine} rankNo={props.showStart ? undefined : props.rankNo} />
      {open && rest.length ? (
        <div data-game-more="1" style={{ marginLeft: 10, paddingLeft: 8, borderLeft: "3px solid " + BLUE, marginBottom: 10 }}>
          {groups.map((gr) => (
            <div key={gr.bt} data-bet-type={gr.bt}>
              <div style={{ fontSize: 13, fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase", color: BLUE, margin: "6px 0" }}>{gr.bt + " · " + gr.picks.length}</div>
              {gr.picks.map((q: Pick) => <AltBet key={q.key} p={q} game={props.g} now={props.now} />)}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface RankedCard { p: Pick; game: Game; rec: WL; cappers: number; net: number; raw: number; contested: boolean; proven: boolean; padded: boolean; my40: number; tier: number; bestN: number }
// K1 (Noel Nov 23): a capper with 20+ graded scanner picks and negative flat-$1 units is "cold".
// A pick whose $1,000+ backers are all cold sorts below every other pick. falcon999/BWmarkets never go cold.
function scannerRecOf(name: string): { n: number; w: number; l: number; units: number; roi?: number | null; cold?: boolean; last20?: Last20 } | null {
  const m = (DATA.scannerRecord && DATA.scannerRecord.cappers) || {};
  const k = (name || "").trim();
  if (m[k]) return m[k];
  const lk = k.toLowerCase();
  const hit = Object.keys(m).find((x: string) => x.toLowerCase() === lk);
  return hit ? m[hit] : null;
}
function last20Of(name: string): Last20 | null {
  const rec = scannerRecOf(name);
  if (rec && rec.last20 && rec.last20.n && rec.last20.dots) return rec.last20;
  const baked = BAKED_LAST20 as Record<string, Last20>;
  const k = (name || "").trim();
  if (baked[k] && baked[k].n) return baked[k];
  const lk = k.toLowerCase();
  const hit = Object.keys(baked).find((x: string) => x.toLowerCase() === lk);
  return hit && baked[hit] && baked[hit].n ? baked[hit] : null;
}
function Last20Dots(props: { name: string }): React.ReactElement | null {
  const r = last20Of(props.name);
  if (!r || !r.n || !r.dots) return null;
  const pnl = (r.pnl >= 0 ? "+" : "") + kMoney(r.pnl);
  return (
    <div data-last20="1" title="Oldest left, newest right · flat $1 at first shown price" style={{ marginTop: 4, maxWidth: "100%" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "center" }}>
        {r.dots.split("").map((d, i) => (
          <span key={i} title={d === "W" ? "Hit" : "Miss"} style={{ width: 7, height: 7, borderRadius: 999, background: d === "W" ? GREEN : RED, flex: "none", display: "inline-block" }} />
        ))}
      </div>
      <div style={{ fontSize: 11, lineHeight: "15px", fontWeight: 750, color: r.pnl >= 0 ? GREEN : RED, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{"Last " + r.n + " settled: " + r.w + "W-" + r.l + "L · " + pnl}</div>
    </div>
  );
}
const LAST20_PRIOR = 10;
function last20Shrink(name: string): number {
  const r = last20Of(name);
  if (!r || !r.n) return -1;
  return (r.w + 0.5 * LAST20_PRIOR) / (r.n + LAST20_PRIOR);
}
function longTermPnlOf(name: string): number | null {
  const c = capperOf(name);
  if (!c) return null;
  const all = qualityNum(c.pnl);
  if (all != null) return all;
  return qualityNum(c.yearlyPnl);
}
function boardRankOf(name: string): number | null {
  const c = capperOf(name);
  if (!c) return null;
  const r = c.ranks || {};
  const nums: number[] = [];
  ["all_time", "yearly", "monthly", "weekly"].forEach((k: string) => {
    const v = r[k];
    if (typeof v === "number" && v > 0) nums.push(v);
  });
  const pr = c.profitRanks || {};
  Object.keys(pr).forEach((board: string) => {
    const row = pr[board];
    if (row && typeof row === "object") {
      Object.keys(row).forEach((k: string) => {
        const v = (row as Record<string, unknown>)[k];
        if (typeof v === "number" && v > 0) nums.push(v);
      });
    } else if (typeof row === "number" && row > 0) nums.push(row);
  });
  return nums.length ? Math.min.apply(null, nums) : null;
}
function veteranDaysOf(name: string): number {
  const c = capperOf(name);
  return c && c.ageDays != null && isFinite(c.ageDays) ? c.ageDays : 0;
}
function last20PnlOf(name: string): number | null {
  const r = last20Of(name);
  return r && r.n ? r.pnl : null;
}
function capperRoiPct(name: string): { roi: number | null; reliable: boolean; n: number } {
  const c = capperOf(name);
  const g = c && c.graded;
  const n = (g && g.n) || 0;
  const vol = c && c.volumeUsd != null && isFinite(c.volumeUsd) ? c.volumeUsd : 0;
  let roi: number | null = null;
  if (g && g.roi != null && n >= 5) roi = g.roi;
  else if (c && vol >= 1000 && c.pnl != null) roi = 100 * c.pnl / vol;
  const reliable = n >= 20 || vol >= 25000 || (n >= 10 && vol >= 10000);
  return { roi, reliable, n };
}
function historyVeteran(name: string): boolean {
  const r = capperRoiPct(name);
  const pnl = longTermPnlOf(name);
  return r.reliable || veteranDaysOf(name) >= 60 || r.n >= 10 || (pnl != null && Math.abs(pnl) >= 50000);
}
function historyScore(name: string): number | null {
  const pnl = longTermPnlOf(name);
  if (pnl == null) return null;
  const logp = Math.log10(1 + Math.max(0, pnl));
  const r = capperRoiPct(name);
  if (r.roi != null && r.reliable) return logp * (1 + Math.max(-0.5, r.roi) / 8);
  return logp;
}
function cmpCapperHistory(a: string, b: string): number {
  const va = historyVeteran(a), vb = historyVeteran(b);
  if (va !== vb) return va ? -1 : 1;
  const sa = historyScore(a), sb = historyScore(b);
  if (sa == null && sb != null) return 1;
  if (sb == null && sa != null) return -1;
  if (sa != null && sb != null && Math.abs(sa - sb) > 1e-9) return sb - sa;
  const pa = longTermPnlOf(a), pb = longTermPnlOf(b);
  if (pa == null && pb != null) return 1;
  if (pb == null && pa != null) return -1;
  if (pa != null && pb != null && pa !== pb) return pb - pa;
  const ra = boardRankOf(a), rb = boardRankOf(b);
  if (ra == null && rb != null) return 1;
  if (rb == null && ra != null) return -1;
  if (ra != null && rb != null && ra !== rb) return ra - rb;
  const da = veteranDaysOf(a), db = veteranDaysOf(b);
  if (da !== db) return db - da;
  const la = last20PnlOf(a), lb = last20PnlOf(b);
  if (la == null && lb != null) return 1;
  if (lb == null && la != null) return -1;
  if (la != null && lb != null && la !== lb) return lb - la;
  return 0;
}
function bestHistoryBacker(p: { backers?: { name: string }[] }): string {
  const bs = p.backers || [];
  if (!bs.length) return "";
  return bs.slice().sort((x, y) => cmpCapperHistory(x.name, y.name))[0].name;
}
function pickHistoryCmp(a: { backers?: { name: string }[] }, b: { backers?: { name: string }[] }): number {
  return cmpCapperHistory(bestHistoryBacker(a), bestHistoryBacker(b));
}
function sortBackersByLast20<T extends { name: string }>(backers: T[]): T[] {
  return backers.slice().sort((a: T, b: T) => cmpCapperHistory(a.name, b.name));
}
function isColdBacker(name: string): boolean {
  const k = (name || "").trim().toLowerCase();
  if (k === "falcon999" || k === "bwmarkets") return false;
  const r = scannerRecOf(name);
  return !!(r && r.cold);
}
function isColdPick(p: Pick): boolean {
  const bs = (p.backers || []).filter((b: Backer) => stakeOk(b.cost, p));
  return bs.length > 0 && bs.every((b: Backer) => isColdBacker(b.name));
}
function ColdChip(props: { p: Pick }): React.ReactElement | null {
  if (!isColdPick(props.p)) return null;
  const b = (props.p.backers || []).find((x: Backer) => isColdBacker(x.name));
  const r = b ? scannerRecOf(b.name) : null;
  const txt = r ? "Cold on scanner " + r.w + "-" + r.l + " · " + (r.units >= 0 ? "+" : "") + r.units.toFixed(1) + "u" : "Cold on scanner";
  return <span data-cold="1" title="This capper's last 20+ graded scanner picks lost money at flat $1, so the pick is ranked at the bottom" style={{ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: "#FEF3C7", color: "#92400E", border: "1.5px solid #F59E0B", fontSize: 12, fontWeight: 850 }}>{"🧊 " + txt}</span>;
}
// ---- Nov 23 (Noel): LIVE-added tag, Fading / You're late, combo boost ----
// Fading: current price is 5c+ BELOW the $1,000+ cappers' average entry -> sorts below non-fading picks.
// You're late: price is 5c+ ABOVE their entry -> label only, no downrank.
const FADE_CENTS = 5;
function entryGapCents(p: Pick): number | null {
  const px = pickPrice(p);
  if (px == null) return null;
  const avgs = (p.backers || []).filter((b: Backer) => stakeOk(b.cost, p) && b.avg != null && (b.avg as number) > 0 && (b.avg as number) < 1).map((b: Backer) => b.avg as number);
  if (!avgs.length) return null;
  const avg = avgs.reduce((a: number, x: number) => a + x, 0) / avgs.length;
  return Math.round((px - avg) * 100);
}
function isFadingPick(p: Pick): boolean { const g = entryGapCents(p); return g != null && g <= -FADE_CENTS; }
function isLatePick(p: Pick): boolean { const g = entryGapCents(p); return g != null && g >= FADE_CENTS; }
function firstAddedTs(p: Pick): number {
  const xs = (p.backers || []).map((b: Backer) => b.addedTs || 0).filter((x: number) => x > 0);
  return xs.length ? Math.min(...xs) : 0;
}
function addedAfterStart(p: Pick, startTs?: number | null): boolean {
  const st = p.startTs || startTs || 0;
  const first = firstAddedTs(p);
  return !!(st && first && first > st);
}
function comboRecOf(name: string): { name?: string; n: number; w: number; l: number; pnl: number; boost?: boolean } | null {
  const m = (DATA.comboRecords && DATA.comboRecords.cappers) || {};
  const lk = (name || "").trim().toLowerCase();
  if (m[lk]) return m[lk];
  const hit = Object.keys(m).find((x: string) => x.toLowerCase() === lk);
  return hit ? m[hit] : null;
}
// Combo boost only when a $1,000+ backer's own Kalshi combo record is positive over 30+ settled combos.
function comboBoostBacker(p: Pick): Backer | null {
  if (!isComboPick(p)) return null;
  const b = (p.backers || []).find((x: Backer) => stakeOk(x.cost, p) && !!(comboRecOf(x.name) || { boost: false }).boost);
  return b || null;
}
const flagChip = (bg: string, fg: string, border: string): React.CSSProperties => ({ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: bg, color: fg, border: "1.5px solid " + border, fontSize: 12, fontWeight: 850 });
interface PublicSlatePick { ticker?: string; yesNo?: string; side?: string; game?: string; startTs?: number; bt?: string; n?: number }
let OTHER_SLATE: PublicSlatePick[] = [];
let OTHER_SLATE_STARTED = false;
const OTHER_SLATE_LISTENERS: Array<() => void> = [];
function useOtherSlate(): PublicSlatePick[] {
  const [rows, setRows] = useState<PublicSlatePick[]>(OTHER_SLATE);
  useEffect(() => {
    const bump = () => setRows(OTHER_SLATE.slice());
    OTHER_SLATE_LISTENERS.push(bump);
    if (!OTHER_SLATE_STARTED) {
      OTHER_SLATE_STARTED = true;
      fetch("https://nfm0984-png.github.io/whale-scanner-kexg2auz/public_slate.json?t=" + Date.now()).then((r) => r.ok ? r.json() : null).then((d: { picks?: PublicSlatePick[] }) => {
        if (d && Array.isArray(d.picks)) { OTHER_SLATE = d.picks; OTHER_SLATE_LISTENERS.forEach((fn) => fn()); }
      }).catch(() => {});
    }
    return () => { const i = OTHER_SLATE_LISTENERS.indexOf(bump); if (i >= 0) OTHER_SLATE_LISTENERS.splice(i, 1); };
  }, []);
  return rows;
}
function normTicker(t?: string | null): string { return (t || "").toUpperCase().replace(/[^A-Z0-9-]/g, ""); }
function normYesNo(y?: string | null): string {
  const u = (y || "").trim().toUpperCase();
  if (u === "Y" || u === "YES" || u.indexOf("BUY YES") >= 0 || /\bYES$/.test(u)) return "YES";
  if (u === "N" || u === "NO" || u.indexOf("BUY NO") >= 0 || /\bNO$/.test(u)) return "NO";
  return u;
}
function slateHitForPick(p: Pick): PublicSlatePick | null {
  const tk = normTicker(p.ticker || (p.view && p.view.ticker));
  if (!tk) return null;
  const hits = OTHER_SLATE.filter((s) => normTicker(s.ticker) === tk);
  if (!hits.length) return null;
  const yn = normYesNo(p.view && p.view.yesNo);
  if (yn) {
    const same = hits.find((s) => normYesNo(s.yesNo) === yn);
    if (same) return same;
  }
  return hits.length === 1 ? hits[0] : null;
}
function gameOfPick(p: Pick): Game | undefined {
  return (DATA.games || []).find((g: Game) => (g.picks || []).some((q: Pick) => q.key === p.key));
}
function splitInfo(p: Pick, game?: Game | null): { oppN: number; oppLabel: string } | null {
  const g = game || gameOfPick(p);
  if (!g) return null;
  const opp = oppositionPicks(p, g);
  let oppN = 0;
  let oppLabel = "";
  opp.forEach((q: Pick) => {
    const n = (q.backers || []).length;
    if (!n) return;
    oppN += n;
    if (!oppLabel) oppLabel = q.big || (q.view && q.view.backing) || "other side";
  });
  if (oppN < 1 || !(p.backers || []).length) return null;
  return { oppN, oppLabel };
}
function PickFlags(props: { p: Pick; startTs?: number | null; game?: Game }): React.ReactElement | null {
  useOtherSlate();
  const p = props.p;
  const out: React.ReactElement[] = [];
  if (addedAfterStart(p, props.startTs)) out.push(<span key="la" data-live-added="1" title="This pick first showed up on the scanner after the game had started" style={flagChip("#FEE2E2", "#B91C1C", "#EF4444")}>{"LIVE · added after start"}</span>);
  const g = entryGapCents(p);
  if (g != null && g <= -FADE_CENTS) out.push(<span key="fd" data-fading="1" title="Price is 5c+ below what the cappers paid, so the market is moving against them. Ranked below non-fading picks." style={flagChip("#F1F5F9", "#475569", "#94A3B8")}>{"📉 Fading · " + Math.abs(g) + "¢ under entry"}</span>);
  else if (g != null && g >= FADE_CENTS) out.push(<span key="lt" data-late="1" title="Price is 5c+ above what the cappers paid. Label only; ranking unchanged." style={flagChip("#FFF7ED", "#9A3412", "#FB923C")}>{"⏰ You're late · +" + g + "¢ over entry"}</span>);
  const cb = comboBoostBacker(p);
  if (cb) { const r = comboRecOf(cb.name); if (r) out.push(<span key="cb" data-combo-boost="1" title="This capper's own Kalshi combos are profitable over 30+ settled combos, so the combo gets a ranking boost" style={flagChip("#ECFDF5", "#047857", "#10B981")}>{"🔗 Combo pro " + r.w + "-" + r.l + " · " + (r.pnl >= 0 ? "+$" : "-$") + (Math.abs(r.pnl) >= 1000 ? (Math.abs(r.pnl) / 1000).toFixed(1) + "k" : String(Math.round(Math.abs(r.pnl))))}</span>); }
  const agreeN = (p.backers || []).length;
  if (agreeN >= 2) out.push(<span key="ag" data-agree="1" title="Two or more cappers who pass the quality filter are on this pick. Label only; ranking unchanged." style={flagChip("#EEF2FF", "#3730A3", "#818CF8")}>{agreeN + " agree"}</span>);
  const split = splitInfo(p, props.game);
  if (split) out.push(<span key="sp" data-split="1" title={"Quality cappers are on both sides of this market — sharp-vs-sharp coin flip. " + split.oppN + " on " + split.oppLabel + "."} style={flagChip("#FFFBEB", "#B45309", "#F59E0B")}>{"Split · vs " + split.oppN + (split.oppLabel ? " on " + split.oppLabel : "")}</span>);
  const both = slateHitForPick(p);
  if (both) out.push(<span key="bo" data-both-scanners="1" title={"A top Polymarket whale is also on this same Kalshi contract" + (both.n ? " (" + both.n + " whale" + (both.n === 1 ? "" : "s") + ")" : "") + "."} style={flagChip("#ECFDF5", "#047857", "#34D399")}>{"Both scanners"}</span>);
  return out.length ? <>{out}</> : null;
}
function FollowFlags(props: { p: FollowPick }): React.ReactElement | null {
  const p = props.p;
  const out: React.ReactElement[] = [];
  if (p.startTs && p.addedTs && p.addedTs > p.startTs) out.push(<span key="la" data-live-added="1" title="This pick first showed up on the scanner after the game had started" style={flagChip("#FEE2E2", "#B91C1C", "#EF4444")}>{"LIVE · added after start"}</span>);
  const g = p.price != null && p.entry != null && p.price > 0 && p.entry > 0 && p.entry < 1 ? Math.round((p.price - p.entry) * 100) : null;
  if (g != null && g <= -FADE_CENTS) out.push(<span key="fd" data-fading="1" title="Price is 5c+ below what the capper paid" style={flagChip("#F1F5F9", "#475569", "#94A3B8")}>{"📉 Fading · " + Math.abs(g) + "¢ under entry"}</span>);
  else if (g != null && g >= FADE_CENTS) out.push(<span key="lt" data-late="1" title="Price is 5c+ above what the capper paid. Label only." style={flagChip("#FFF7ED", "#9A3412", "#FB923C")}>{"⏰ You're late · +" + g + "¢ over entry"}</span>);
  return out.length ? <>{out}</> : null;
}
function hideSplitsOnGames(games: Game[]): { games: Game[]; hidden: number } {
  const hidden: Record<string, boolean> = {};
  const out = games.map((g: Game) => {
    const picks = (g.picks || []).filter((p: Pick) => !splitInfo(p, g));
    if (picks.length !== (g.picks || []).length) hidden[g.id] = true;
    return { ...g, picks };
  }).filter((g: Game) => (g.picks || []).length > 0);
  return { games: out, hidden: Object.keys(hidden).length };
}
function splitHiddenNote(n: number): string {
  return n ? (n + " split game" + (n === 1 ? "" : "s") + " hidden") : "";
}
function hiddenSplitGames(games: Game[]): number {
  const ids: Record<string, boolean> = {};
  games.forEach((g: Game) => (g.picks || []).forEach((p: Pick) => { if (splitInfo(p, g)) ids[g.id] = true; }));
  return Object.keys(ids).length;
}
function rankedPicks(games: Game[]): RankedCard[] {
  const cards: RankedCard[] = [];
  const seen: Record<string, boolean> = {};
  games.forEach((game: Game) => {
    (game.picks || []).forEach((p: Pick) => {
      if (!hasMy40Backer(p) || !(p.backers || []).length) return;
      if (splitInfo(p, game)) return;
      if (seen[p.key]) return;
      seen[p.key] = true;
      const n = netOf(p, game);
      cards.push({ p, game, rec: n.ownRec, cappers: n.my40 || n.ownN, net: n.net, raw: n.raw, contested: n.contested, proven: n.proven, padded: n.padded, my40: n.my40, tier: n.tier, bestN: n.bestN });
    });
  });
  // Ranked: keep every pick. Long-term dollar PnL and leaderboard rank first, veterans above newbies. Last-20 dollar PnL (not raw W-L, so short-odds grinders don't float) is only a tiebreaker.
  return cards.sort((a: RankedCard, b: RankedCard) => pickHistoryCmp(a.p, b.p) || (Number(isColdPick(a.p)) - Number(isColdPick(b.p))) || (Number(isFadingPick(a.p)) - Number(isFadingPick(b.p))) || rankCmpNet(netOf(a.p, a.game), netOf(b.p, b.game)) || ((a.p.key < b.p.key) ? -1 : 1));
}
function pickRankMap(games: Game[]): Record<string, number> {
  const m: Record<string, number> = {};
  rankedPicks(games).forEach((c: RankedCard, i: number) => { m[c.p.key] = i + 1; });
  return m;
}
function rankedLists(games: Game[]): { list: RankedCard[]; top: RankedCard[]; others: RankedCard[]; small: RankedCard[]; contested: RankedCard[]; total: number } {
  const list = rankedPicks(games);
  return { list, top: list, others: [], small: [], contested: list.filter((c: RankedCard) => c.contested), total: list.length };
}
function gameMatchesQuery(g: Game, q: string): boolean {
  if (!q) return true;
  if ((g.game || "").toLowerCase().includes(q) || (g.league || "").toLowerCase().includes(q)) return true;
  return g.picks.some((p: Pick) => (p.big + " " + p.sub + " " + (p.view.backing || "")).toLowerCase().includes(q) || p.backers.some((b: Backer) => (b.name || "").toLowerCase().includes(q)));
}
function ComingUpTab(props: { games: Game[]; now: number; query?: string; filter?: string }) {
  const q = (props.query || "").trim().toLowerCase();
  const split = hideSplitsOnGames(props.games);
  const ranks = pickRankMap(split.games);
  const games = split.games.filter((g: Game) => gameMatchesQuery(g, q)).filter((g: Game) => props.filter === "live" ? g.live : props.filter === "upcoming" ? !g.live : true);
  const splitNote = splitHiddenNote(split.hidden);
  const live = games.filter((g: Game) => g.live).sort((a, b) => (a.startTs || 0) - (b.startTs || 0) || (a.id < b.id ? -1 : 1));
  const up = games.filter((g: Game) => !g.live).sort((a, b) => (a.startTs || 1e12) - (b.startTs || 1e12) || (a.id < b.id ? -1 : 1));
  const rankOf = (g: Game) => {
    const main = bestPickFirst(g.picks || [], g)[0];
    return main && ranks[main.key] ? ranks[main.key] : undefined;
  };
  return (
    <div>
      {games.length === 0 ? <EmptyState title={props.games.length === 0 && !split.hidden ? "No public Kalshi books right now" : "No picks match that filter"} body={props.games.length === 0 && !split.hidden ? "None of the trackable cappers has a $1,000+ open sports position or profile post starting within 24 hours." : "Try another search or clear the filter."} /> : null}
      {splitNote ? <div data-splits-hidden="1" style={{ fontSize: 13, fontWeight: 700, color: "#B45309", margin: "0 2px 8px" }}>{splitNote}</div> : null}
      {live.length ? <div data-live-head="1" style={{ fontSize: 18, fontWeight: 900, margin: "4px 2px 2px", color: NAVY }}>{"Already started (" + live.length + ")"}</div> : null}
      {live.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart rankNo={rankOf(g)} />)}
      {up.length ? <div data-all-today="1" style={{ fontSize: 18, fontWeight: 900, margin: "10px 2px 2px", color: NAVY }}>{"Upcoming (" + up.length + ")"}</div> : null}
      {up.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart rankNo={rankOf(g)} />)}
    </div>
  );
}
function BestCappersRoster() {
  const caps = ((DATA.following || {}).cappers || []) as FollowCapper[];
  if (!caps.length) return null;
  return (
    <details data-best-cappers-roster="1" style={{ marginTop: 18, marginBottom: 8, borderRadius: 14, border: "1.5px solid #DDD6FE", background: "#FFFFFF", padding: "8px 12px" }}>
      <summary style={{ cursor: "pointer", fontWeight: 800, fontSize: 14, color: BLUE_INK }}>{"Best Cappers database · " + caps.length + " of " + ((capperDatabase().target) || TARGET_FOLLOW) + " · tap to expand"}</summary>
      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
        {caps.map((c: FollowCapper, i: number) => (
          <div key={c.nickname} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, fontWeight: 700, color: NAVY, padding: "4px 0", borderTop: i ? "1px solid #EDE9FE" : undefined }}>
            <span style={{ overflowWrap: "anywhere" }}>{(i + 1) + ". " + c.nickname}</span>
            <span style={{ color: "#64748B", fontVariantNumeric: "tabular-nums", flex: "none" }}>{((c.closedN || ((c.closedW || 0) + (c.closedL || 0))) ? ((c.closedW || 0) + "–" + (c.closedL || 0)) : (c.n ? ((c.w || 0) + "–" + (c.l || 0)) : "no W–L")) + (c.open ? " · " + c.open + " open" : "")}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

interface ScorecardPick { result?: string; pnl?: number | null; capper?: string; capperNote?: string; cappers?: string[]; agree?: number; yesNo?: string; label?: string; q?: string; side?: string; ticker?: string; combo?: boolean }
interface ScorecardBucket { label: string; w?: number; l?: number; pending?: number; pnl?: number | null; n?: number }
interface ScorecardDay { date?: string; label?: string; w?: number; l?: number; pending?: number; pnl?: number | null; n?: number }
interface Scorecard { date?: string; label?: string; updatedAt?: string; w?: number; l?: number; pending?: number; pnl?: number | null; pnlNote?: string; pnlPartial?: boolean; hiddenSplits?: number; breakdown?: ScorecardBucket[]; history?: ScorecardDay[]; picks?: ScorecardPick[] }
function moneyAbs(n: number): string {
  const a = Math.abs(n);
  if (a >= 1000) return (a / 1000).toFixed(a >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return String(Math.round(a));
}
function scorecardMoney(n: number | null | undefined): string {
  if (n == null || !isFinite(Number(n)) || Math.abs(n) < 0.005) return "";
  const sign = n >= 0 ? "+$" : "-$";
  const a = Math.abs(n);
  if (a >= 1000) return sign + (a / 1000).toFixed(a >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return sign + a.toFixed(2).replace(/\.00$/, "");
}
function scorecardYesNo(row: ScorecardPick): string {
  const u = ((row.yesNo || row.side || "") + "").trim().toUpperCase();
  if (u === "Y" || u === "YES" || u.indexOf("BUY YES") >= 0) return "YES";
  if (u === "N" || u === "NO" || u.indexOf("BUY NO") >= 0) return "NO";
  return "";
}
function ScorecardHistory(props: { sc: Scorecard }): React.ReactElement | null {
  const days = props.sc.history || [];
  if (!days.length) return null;
  return (
    <div data-scorecard-history="1" style={{ marginTop: 14, paddingTop: 10, borderTop: "1.5px solid #EDE9FE" }}>
      <div style={{ fontSize: 13, fontWeight: 850, color: "#475569", marginBottom: 6 }}>{"Last 7 days (" + days.length + " day" + (days.length === 1 ? "" : "s") + " tracked)"}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {days.slice().reverse().map((d: ScorecardDay) => {
          const dol = scorecardMoney(d.pnl);
          return (
            <div key={d.date || d.label} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 13, fontWeight: 750, color: "#0F172A" }}>
              <span>{d.label || d.date || ""}</span>
              <span style={{ flex: "none", fontVariantNumeric: "tabular-nums" }}>{(d.w || 0) + "–" + (d.l || 0) + (d.pending ? " · " + d.pending + " pend" : "") + (dol ? " · " + dol : "")}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
function ScorecardBreakdown(props: { sc: Scorecard }): React.ReactElement | null {
  const rows = props.sc.breakdown || [];
  if (!rows.length) return null;
  return (
    <div data-scorecard-breakdown="1" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "10px 0 8px" }}>
      {rows.map((b: ScorecardBucket) => {
        const dol = scorecardMoney(b.pnl);
        return (
          <div key={b.label} style={{ flex: "1 1 150px", minWidth: 140, border: "1.5px solid #DDD6FE", borderRadius: 12, padding: "8px 10px", background: "#FAF8FF" }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: "#64748B", letterSpacing: "0.04em", textTransform: "uppercase" }}>{b.label}</div>
            <div style={{ fontSize: 15, fontWeight: 850, color: NAVY, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{(b.w || 0) + "–" + (b.l || 0)}{(b.pending ? " · " + b.pending + " pend" : "") + (dol ? " · " + dol : "")}</div>
          </div>
        );
      })}
    </div>
  );
}
function ScorecardBlock(): React.ReactElement {
  const [sc, setSc] = useState<Scorecard | null | undefined>(undefined);
  useEffect(() => {
    fetch("scorecard.json?t=" + Date.now()).then((r) => r.ok ? r.json() : null).then((d: Scorecard) => { setSc(d && (d.date || d.label) ? d : null); }).catch(() => { setSc(null); });
  }, []);
  if (sc === undefined) return <Section heading="Scorecard" caption="Loading yesterday’s scanner picks…"><Text>Loading…</Text></Section>;
  if (!sc) return <EmptyState title="No scorecard yet" body="Yesterday’s scanner picks will show here after the daily scorecard job runs (about 6:35 AM PT)." />;
  const w = sc.w || 0, l = sc.l || 0, pending = sc.pending || 0;
  const pnl = sc.pnl;
  const pnlStr = scorecardMoney(pnl);
  const heading = "Yesterday · " + w + "–" + l + (pending ? " · " + pending + " pending" : "") + (pnlStr ? " · " + pnlStr : "") + (sc.pnlPartial ? " (partial $)" : "");
  return (
    <Section heading={heading} caption={(sc.label || "Yesterday") + (sc.pnlNote ? " · " + sc.pnlNote : "") + (sc.updatedAt ? " · updated " + sc.updatedAt : "")}>
      <ScorecardBreakdown sc={sc} />
      {sc.hiddenSplits ? <div data-splits-hidden="1" style={{ fontSize: 13, fontWeight: 700, color: "#B45309", margin: "0 0 8px" }}>{splitHiddenNote(sc.hiddenSplits)}</div> : null}
      {(sc.picks || []).length === 0 ? <EmptyState title="No scanner picks yesterday" body="No scanner picks started yesterday in PT." /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
          {(sc.picks || []).map((row: ScorecardPick, i: number) => {
            const res = row.result || "pending";
            const rawTitle = row.label || row.q || row.capper || ("Pick " + (i + 1));
            const title = rawTitle.indexOf("KX") === 0 ? (row.q || row.capper || rawTitle) : rawTitle;
            const yn = scorecardYesNo(row);
            const who = row.capperNote || (row.agree && row.agree > 1 ? (row.agree + " cappers") : (row.capper || ""));
            const dol = scorecardMoney(row.pnl);
            const color = res === "W" ? "#047857" : res === "L" ? "#B91C1C" : "#64748B";
            return (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 13, fontWeight: 700, color: "#0F172A" }}>
                <span style={{ overflowWrap: "anywhere" }}><span style={{ color, fontWeight: 850, marginRight: 8 }}>{res + " "}</span>{yn ? <span data-yesno={yn} style={{ display: "inline-block", marginRight: 6, padding: "0 6px", borderRadius: 6, background: yn === "YES" ? "#ECFDF5" : "#F1F5F9", color: yn === "YES" ? "#047857" : "#334155", fontWeight: 900, fontSize: 11, letterSpacing: "0.04em" }}>{yn}</span> : null}{title}{who && title !== who ? " · " + who : ""}</span>
                {dol ? <span style={{ color, flex: "none", fontVariantNumeric: "tabular-nums" }}>{dol}</span> : null}
              </div>
            );
          })}
        </div>
      )}
      <ScorecardHistory sc={sc} />
    </Section>
  );
}
function ScorecardTab(): React.ReactElement {
  return <ScorecardBlock />;
}

function RankedTab(props: { games: Game[]; now: number; query?: string; filter?: string }) {
  const q = (props.query || "").trim().toLowerCase();
  const games = todayGames(props.games, props.now).filter((g: Game) => gameMatchesQuery(g, q)).filter((g: Game) => props.filter === "live" ? g.live : props.filter === "upcoming" ? !g.live : true);
  const list = rankedPicks(games);
  const comboN = list.filter((c: RankedCard) => isComboPick(c.p)).length;
  const singleN = list.length - comboN;
  const splitNote = splitHiddenNote(hiddenSplitGames(games));
  return (
    <div>
      <Section heading={"Ranked Picks · " + list.length + " picks · " + singleN + (singleN === 1 ? " single" : " singles") + " · " + comboN + (comboN === 1 ? " combo" : " combos")} caption={"Every open $1,000+ single and combo, best first. Higher-ranked Best Cappers surface at the top. From public positions or profile posts. Today in PT; after 7pm PT, tomorrow is included." + (splitNote ? " · " + splitNote : "")}>
        {list.length === 0 ? <EmptyState title={todayGames(props.games, props.now).length === 0 ? "No Ranked Picks in this window" : "No picks match that filter"} body={todayGames(props.games, props.now).length === 0 ? "No capper has a $1,000+ trackable sports pick starting today in PT (after 7pm PT, tomorrow is included)." : "Try another search or clear the filter."} /> : null}
        {list.map((c: RankedCard, i: number) => (
          <UCard key={c.p.key} p={{ ...c.p, backers: sortBackersByLast20(c.p.backers || []) }} game={c.game} now={props.now} stake="$2–4" rankNo={i + 1} />
        ))}
      </Section>
      <BestCappersRoster />
    </div>
  );
}
function FollowingTab(props: { now: number; query?: string; filter?: string }) {
  const F = DATA.following || { cappers: [], picks: [], startedAt: "", recorded: 0, graded: 0 };
  const caps = F.cappers || [];
  const picks = (F.picks || []).filter((fp: FollowPick) => !followPickIsFinished(fp, props.now) && stakeOk(fp.cost, fp) && capperShownOk(fp.nickname, props.now, undefined, fp.league) && pickPayoutOk(fp));
  const byName: Record<string, FollowPick[]> = {};
  picks.forEach((fp: FollowPick) => { (byName[fp.nickname] = byName[fp.nickname] || []).push(fp); });
  Object.keys(byName).forEach((k: string) => {
    byName[k].sort((a: FollowPick, b: FollowPick) => {
      const al = !!(a.startTs && a.startTs <= props.now), bl = !!(b.startTs && b.startTs <= props.now);
      return (al === bl ? 0 : al ? -1 : 1) || ((a.startTs || 1e12) - (b.startTs || 1e12));
    });
  });
  const ordered = caps.slice().sort((a: FollowCapper, b: FollowCapper) => {
    const ao = (byName[a.nickname] || []).length, bo = (byName[b.nickname] || []).length;
    if (ao !== bo) return bo - ao;
    const an = (a.w || 0) + (a.l || 0), bn = (b.w || 0) + (b.l || 0);
    if (an && bn && a.hitPct != null && b.hitPct != null && a.hitPct !== b.hitPct) return (b.hitPct as number) - (a.hitPct as number);
    return (a.nickname || "").localeCompare(b.nickname || "");
  });
  const tw = caps.reduce((a: number, c: FollowCapper) => a + (c.w || 0), 0);
  const tl = caps.reduce((a: number, c: FollowCapper) => a + (c.l || 0), 0);
  const tn = tw + tl;
  const hit = tn ? Math.round((1000 * tw) / tn) / 10 : null;
  const trialTone = recTone(tw, tl);
  const q = (props.query || "").trim().toLowerCase();
  let shown = ordered.filter((c: FollowCapper) => !q || (c.nickname || "").toLowerCase().includes(q));
  if (props.filter === "graded") shown = shown.filter((c: FollowCapper) => (c.w || 0) + (c.l || 0) > 0);
  if (props.filter === "open") shown = shown.filter((c: FollowCapper) => (byName[c.nickname] || []).length > 0);
  return (
    <div>
      <div data-trial-box="1" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 12, background: "#FFFBEB", border: "1px solid #FDE68A", marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 850, letterSpacing: "0.06em", textTransform: "uppercase", color: "#92400E" }}>Copy trial</span>
        <RecordPill w={tw} l={tl} />
        {hit != null ? <span style={{ fontSize: 13, fontWeight: 800, color: trialTone.fg }}>{hit}% hit</span> : null}
        <span style={{ fontSize: 13, fontWeight: 650, color: "#78716C" }}>
          {F.startedAt ? ("Since " + F.startedAt + ((F.graded || 0) ? " · " + F.graded + " graded" : (F.recorded || 0) ? " · " + F.recorded + " recorded" : "")) : "Starts when the first followed pick is recorded."}
        </span>
      </div>
      {picks.length === 0 && caps.length ? <EmptyState title="No open followed picks right now" body={"Followed cappers don’t have an open $1,000+ traditional-sports position or profile post in this window. Finished games drop off; the trial still grades what was already recorded."} /> : null}
      {picks.length === 0 && !caps.length ? <EmptyState title="Best Cappers is waiting on followed cappers" body={"The followed-capper list is empty. Seed data/cappers_pinned.json or drop /workspace/kalshi-top10-cappers.json and the next scan will fill this tab."} /> : null}
      {shown.length === 0 && (q || props.filter) && caps.length ? <EmptyState title="No followed cappers match that filter" body="Try another search or clear the filter." /> : null}
      {shown.map((c: FollowCapper) => {
        const cap = capperOf(c.nickname);
        const g = gradedWL(cap);
        const settled = !!(g && (g.w + g.l) > 0);
        const mine = byName[c.nickname] || [];
        const hasLive = mine.some((fp: FollowPick) => !!(fp.startTs && fp.startTs <= props.now));
        const head = sportsHeadline(cap);
        const trialPct = (c.w + c.l) ? (c.hitPct != null ? c.hitPct : Math.round((1000 * c.w) / (c.w + c.l)) / 10) : null;
        return (
          <CapperShell key={c.nickname} live={hasLive} followed={true}>
            <div data-trial-capper={c.nickname} style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <Face name={c.nickname} size={44} />
              <div style={{ flex: 1, minWidth: 0 }}>
                {cap && cap.profileUrl ? (
                  <a href={cap.profileUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 18, fontWeight: 850, color: NAVY, textDecoration: "none", overflowWrap: "anywhere" }}>{c.nickname} ↗</a>
                ) : (
                  <div style={{ fontSize: 18, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}</div>
                )}
                <div style={{ fontSize: 13, fontWeight: 800, color: recTone(c.w || 0, c.l || 0).fg, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
                  {c.n ? ((c.w + "–" + c.l) + " copy trial" + (trialPct != null ? " · " + trialPct + "% hit" : "")) : (isLeaderboardEarner(cap) ? "Leaderboard earner" : "Copy trial · no grades yet")}
                  {(c.hidden && !c.postsVisible && !c.positionsVisible) ? " · book hidden" : (pickSourceLabel(c.pickSource) ? " · " + pickSourceLabel(c.pickSource) : "")}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: head.color, marginTop: 2 }}>{settled ? ("Sports tape " + head.text) : head.text}</div>
              </div>
              {trialPct != null ? <WinRing pct={trialPct} /> : (settled ? <WinRing pct={Math.round(100 * g!.w / (g!.w + g!.l))} /> : null)}
              <Chip bg={mine.length ? GREEN : "#F1F5F9"} color={mine.length ? "#FFFFFF" : "#475569"}>{mine.length === 1 ? "1 pick" : mine.length + " picks"}</Chip>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 8 }}>
              <TierChip tier="Best Cappers" />
              {g && g.sample === "small" ? <Chip bg="#FEF3C7" color={AMBER}>Small sample</Chip> : null}
              <RankChips ranks={cap && cap.ranks} />
              {c.open ? <Chip bg={BLUE_BRIGHT} color="#FFFFFF">{c.open} open</Chip> : null}
            </div>
            {cap ? <CapperStatRow c={cap} /> : null}
            {mine.length ? mine.map((fp: FollowPick) => <FollowPickMini key={c.nickname + "|" + fp.ticker + "|" + fp.yesNo} p={fp} now={props.now} />) : <div style={{ fontSize: 13, fontWeight: 650, color: (c.hidden && !c.postsVisible && !c.positionsVisible) ? AMBER : "#64748B", marginTop: 10 }}>{bookHiddenMessage(c)}</div>}
          </CapperShell>
        );
      })}
    </div>
  );
}
function capRankTuple(c: Capper): number[] {
  const g = gradedWL(c);
  const w = g ? g.w : 0, l = g ? g.l : 0, n = (g && g.n) ? g.n : (w + l);
  const wr = n ? w / n : -1;
  const veteran = n >= 10 ? 0 : n >= 5 ? 1 : n > 0 ? 2 : 3;
  const pnl = c.pnl == null ? -1e15 : c.pnl;
  const roi = (g && g.roi != null) ? g.roi : -1e9;
  return [veteran, -wr, -n, -roi, -pnl];
}
function sortCappers(caps: Capper[]): Capper[] {
  return caps.slice().sort((a: Capper, b: Capper) => {
    const ra = dbRankOf(a.nickname), rb = dbRankOf(b.nickname);
    if (ra !== rb) return ra - rb;
    const ka = capRankTuple(a), kb = capRankTuple(b);
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
    return (a.nickname || "").localeCompare(b.nickname || "");
  });
}
function CapperCard(props: { c: Capper; now: number; rank: number; filter?: string }) {
  const c = props.c;
  const g = gradedWL(c);
  const settled = !!(g && (g.w + g.l) > 0);
  const head = sportsHeadline(c);
  const allPicks = openPicksFor(c.nickname, props.now);
  const picks = allPicks.filter((x) => props.filter === "live" ? !!x.game.live : props.filter === "upcoming" ? !x.game.live : true);
  const hasLive = picks.some((x) => !!x.game.live || !!(x.p.startTs && x.p.startTs <= props.now));
  const wr = settled ? Math.round(100 * g!.w / (g!.w + g!.l)) : null;
  const src = pickSourceLabel(c.pickSource);
  const closed = settled ? ((g!.w + "–" + g!.l) + (g!.roi != null ? (" · " + (g!.roi >= 0 ? "+" : "") + Math.round(g!.roi) + "% ROI") : "")) : "no closed grade yet";
  const openPos = c.openPositions != null ? c.openPositions : allPicks.length;
  return (
    <CapperShell live={hasLive} followed={true}>
      <div data-capper={c.nickname} style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <div style={{ fontSize: 18, fontWeight: 850, color: BLUE, minWidth: 28 }}>{"#" + (dbRankOf(c.nickname) < 9999 ? dbRankOf(c.nickname) : props.rank)}</div>
        <Face name={c.nickname} size={44} />
        <div style={{ flex: 1, minWidth: 0 }}>
          {c.profileUrl ? (
            <a href={c.profileUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 18, fontWeight: 850, color: NAVY, textDecoration: "none", overflowWrap: "anywhere" }}>{c.nickname} ↗</a>
          ) : (
            <div style={{ fontSize: 18, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}</div>
          )}
          <div style={{ fontSize: 13, fontWeight: 800, color: head.color, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{(c.pnl != null ? ((c.pnl >= 0 ? "+" : "") + kMoney(c.pnl) + " official profit · ") : "") + "Closed " + closed}</div>
          <Last20Dots name={c.nickname} />
        </div>
        {wr != null ? <WinRing pct={wr} /> : null}
        <Chip bg={picks.length ? GREEN : "#F1F5F9"} color={picks.length ? "#FFFFFF" : "#475569"}>{picks.length === 1 ? "1 pick" : picks.length + " picks"}</Chip>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 8 }}>
        {src ? <Chip bg="#EDE9FE" color="#5B21B6">{src}</Chip> : null}
        {openPos ? <Chip bg={BLUE_BRIGHT} color="#FFFFFF">{openPos} open position{openPos === 1 ? "" : "s"}</Chip> : null}
        {g && (g.formW || g.formL) ? <Chip bg="#F8FAFC" color="#334155">{"Recent " + (g.formW || 0) + "–" + (g.formL || 0)}</Chip> : null}
        {g && g.sample === "small" ? <Chip bg="#FEF3C7" color={AMBER}>Small sample</Chip> : (settled && (g!.n || 0) >= 10 ? <Chip bg={GREEN} color="#FFFFFF">Veteran</Chip> : (settled ? <Chip bg={GREEN} color="#FFFFFF">{(g!.n || (g!.w + g!.l)) + " graded"}</Chip> : null))}
        {c.pnl != null && c.pnl < 0 ? <Chip bg="#FEE2E2" color={RED}>Negative profit</Chip> : null}
        <RankChips ranks={c.ranks} />
      </div>
      <CapperStatRow c={c} />
      {isHiddenBook(c) ? <div style={{ fontSize: 13, fontWeight: 700, color: AMBER, marginTop: 10 }}>{bookHiddenMessage(c)}</div> : picks.length ? picks.map((x) => <CapperPickMini key={c.nickname + "|" + x.p.key} p={x.p} game={x.game} now={props.now} backerName={c.nickname} />) : <div style={{ fontSize: 13, fontWeight: 650, color: "#64748B", marginTop: 10 }}>{c.pickCount ? "Open picks are under the $1,000 minimum, already started and dropped, or outside today’s window." : "No open $1,000+ single or combo in the window."}</div>}
    </CapperShell>
  );
}
function CappersTab(props: { now: number; query?: string; filter?: string }) {
  const caps = sortCappers((DATA.cappers || []).slice());
  const q = (props.query || "").trim().toLowerCase();
  let shown = caps.filter((c: Capper) => !q || (c.nickname || "").toLowerCase().includes(q));
  if (props.filter === "wl") shown = shown.filter((c: Capper) => { const g = gradedWL(c); return !!(g && (g.w + g.l) > 0); });
  if (props.filter === "open") shown = shown.filter((c: Capper) => openPicksFor(c.nickname, props.now).length > 0);
  if (shown.length === 0) {
    return <EmptyState title={caps.length === 0 ? "No trackable cappers right now" : "No cappers match that filter"} body={caps.length === 0 ? "The list only includes names whose public positions or profile posts we can actually copy." : "Try another search or clear the filter."} />;
  }
  return (
    <div>
      <div style={{ fontSize: 18, fontWeight: 850, color: NAVY, margin: "18px 0 4px" }}>{"Best Cappers · " + shown.length + " of " + ((capperDatabase().target) || TARGET_FOLLOW)}</div>
      <div style={{ fontSize: 13, fontWeight: 650, color: "#64748B", margin: "0 0 12px", lineHeight: "18px" }}>{shown.length < ((capperDatabase().target) || TARGET_FOLLOW) ? ("Persistent good-only database, rechecked every 5 minutes. " + shown.length + " currently qualify with a winning record and official profit — losing books are not added just to fill the list of " + ((capperDatabase().target) || TARGET_FOLLOW) + ".") : "Persistent good-only database, rechecked every 5 minutes. Ranked by closed-position grade, veterans first."}</div>
      {shown.map((c: Capper, i: number) => <CapperCard key={c.nickname} c={c} now={props.now} rank={i + 1} />)}
    </div>
  );
}


function Ico(props: { children: ReactNode; size?: number }) {
  const s = props.size || 16;
  return <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{props.children}</svg>;
}
const IconCalendar = () => <Ico><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></Ico>;
const IconRefresh = () => <Ico><path d="M23 4v6h-6" /><path d="M1 20v-6h6" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Ico>;
const IconBolt = () => <Ico><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></Ico>;
const IconList = () => <Ico><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></Ico>;
const IconUsers = () => <Ico><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></Ico>;
const IconStack = () => <Ico><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" /></Ico>;
const IconChart = () => <Ico><path d="M3 3v18h18" /><path d="M7 14l4-4 4 4 6-6" /></Ico>;
const IconTrophy = () => <Ico><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z" /><path d="M17 6h2a3 3 0 0 1 0 6h-2M7 6H5a3 3 0 0 0 0 6h2" /></Ico>;
const IconStar = () => <Ico><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14 2 9.27l6.91-1.01L12 2z" /></Ico>;
const IconSearch = () => <Ico size={16}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></Ico>;

function DashStat(props: { label: string; value: string; sub?: string; color: string; icon: ReactNode }) {
  return (
    <div data-dash-stat={props.label} style={{ background: NAVY, color: "#FFFFFF", borderRadius: 16, padding: "14px 16px", display: "flex", alignItems: "center", gap: 12, minHeight: 76, boxShadow: "0 10px 24px rgba(17,8,31,0.12)" }}>
      <div style={{ width: 40, height: 40, borderRadius: 12, background: props.color, display: "flex", alignItems: "center", justifyContent: "center", color: "#FFFFFF", flex: "0 0 auto" }}>{props.icon}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#C4B5FD", letterSpacing: "0.02em" }}>{props.label}</div>
        <div style={{ fontSize: 26, fontWeight: 900, letterSpacing: "-0.03em", lineHeight: "30px", fontVariantNumeric: "tabular-nums" }}>{props.value}</div>
        {props.sub ? <div style={{ fontSize: 11, fontWeight: 650, color: "#DDD6FE", marginTop: 1 }}>{props.sub}</div> : null}
      </div>
    </div>
  );
}

function StatusRow(props: { label: string; status: string; tone: "ok" | "public" | "muted" | "warn" }) {
  const color = props.tone === "ok" ? "#4ADE80" : props.tone === "public" ? "#7DD3FC" : props.tone === "warn" ? "#FBBF24" : "#94A3B8";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline", padding: "8px 0", borderBottom: "1px solid rgba(148,163,184,0.16)" }}>
      <span style={{ fontSize: 13, fontWeight: 650, color: "#E2E8F0" }}>{props.label}</span>
      <span style={{ fontSize: 13, fontWeight: 800, color, textAlign: "right" }}>{props.status}</span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<"coming" | "following" | "ranked" | "cappers" | "scorecard">(() => {
    try {
      const t = new URLSearchParams(window.location.search).get("tab");
      if (t === "coming" || t === "following" || t === "ranked" || t === "cappers" || t === "scorecard") return t;
    } catch (e) {}
    return "ranked";
  });
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Math.round(Date.now() / 1000));
  useEffect(() => {
    const id = setInterval(() => setNow(Math.round(Date.now() / 1000)), 15000);
    return () => clearInterval(id);
  }, []);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [clock, setClock] = useState(0);
  const [sheet, setSheet] = useState<"" | "scan">("");
  const [hasKey, setHasKey] = useState<boolean>(() => !!accessKey());
  const [keyText, setKeyText] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const games = useMemo(() => openGames(now), [now, tick]);
  const comingN = games.reduce((n: number, g: Game) => n + g.picks.length, 0);
  const cov = (DATA.source && DATA.source.coverage) || {};
  const followN = ((DATA.following && DATA.following.picks) || []).filter((fp: FollowPick) => !followPickIsFinished(fp, now) && stakeOk(fp.cost, fp) && capperShownOk(fp.nickname, now, undefined, fp.league) && pickPayoutOk(fp)).length;
  const applyData = (data: Data) => {
    DATA = data;
    (window as any).__DATA = data;
    setNow(Math.round(Date.now() / 1000));
    setTick((n) => n + 1);
    setUpdatedAt(formatNowPt());
  };
  const onRefresh = () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshErr(null);
    const t0 = Date.now();
    setJob({ mode: "refresh", phase: "loading", msg: "Fetching the latest scan data…", t0 });
    fetchLatestData().then((data) => {
      applyData(data);
      const stamp = data.followCheckedAt || data.scannedAt || formatNowPt();
      setJob({ mode: "refresh", phase: "done", msg: "Updated " + formatNowPt() + " · " + stamp, t0 });
    }).catch((e: any) => {
      const msg = String((e && e.message) || "Couldn't refresh. Try again.");
      setRefreshErr(msg);
      setJob({ mode: "refresh", phase: "error", msg, t0 });
    }).finally(() => setRefreshing(false));
  };
  const scanBusy = !!job && job.mode === "scan" && (job.phase === "starting" || job.phase === "queued" || job.phase === "in_progress" || job.phase === "loading");
  const busy = refreshing || scanBusy;
  useEffect(() => { if (!scanBusy) return; const id = setInterval(() => setClock((x) => x + 1), 1000); return () => clearInterval(id); }, [scanBusy]);
  void clock;
  const followScan = async (runId: number, t0: number) => {
    const before = DATA.ts || 0;
    for (let i = 0; i < 80; i++) {
      await sleep(i === 0 ? 3000 : 8000);
      let r: Response;
      try { r = await ghApi("/actions/runs/" + runId); } catch (e) { continue; }
      if (!r.ok) continue;
      const run = await r.json();
      if (run.status !== "completed") {
        setJob({ mode: "scan", phase: run.status === "in_progress" ? "in_progress" : "queued", msg: run.status === "in_progress" ? "Scanning Kalshi books…" : "Waiting for a GitHub server to pick it up…", t0, url: run.html_url });
        continue;
      }
      if (run.conclusion !== "success") { setJob({ mode: "scan", phase: "error", msg: "Scan failed on GitHub (" + run.conclusion + "). Your current data is unchanged.", t0, url: run.html_url }); return; }
      setJob({ mode: "scan", phase: "loading", msg: "Done. Loading the new data…", t0, url: run.html_url });
      for (let k = 0; k < 24; k++) {
        try {
          const data = await fetchLatestData();
          if ((data.ts || 0) !== before) { applyData(data); setJob({ mode: "scan", phase: "done", msg: "Updated " + formatNowPt(), t0, url: run.html_url }); return; }
        } catch (e) { /* retry */ }
        await sleep(5000);
      }
      setJob({ mode: "scan", phase: "done", msg: "Scan finished. Tap Refresh if the new data isn’t here yet.", t0, url: run.html_url });
      return;
    }
    setJob({ mode: "scan", phase: "error", msg: "Started, but the run is taking longer than expected. Open GitHub or tap Refresh later.", t0 });
  };
  const findRun = async (t0: number, repo?: string): Promise<{ id: number; url?: string } | null> => {
    for (let i = 0; i < 12; i++) {
      await sleep(4000);
      try {
        const r = await ghApi("/actions/runs?event=workflow_dispatch&per_page=5", { repo: repo || GH_REPO });
        if (r.ok) {
          const j = await r.json();
          const run = (j.workflow_runs || []).find((x: { created_at?: string; id?: number; html_url?: string }) => Date.parse(x.created_at || "") >= t0 - 90000);
          if (run && run.id) return { id: run.id, url: run.html_url };
        }
      } catch (e) { /* retry */ }
    }
    return null;
  };
  const askRunOnGitHub = (t0: number) => {
    // This device token can read Kalshi Actions and write whale Actions, but it cannot
    // dispatch, commit, or repository-dispatch on kalshi-scanner. A one-tap GitHub link
    // is the only path that starts a scan without new permissions.
    setJob({ mode: "scan", phase: "needs_github", msg: "This key can’t start a scan from the page. Run it on GitHub — one tap.", t0, url: SCAN_WORKFLOW_URL });
  };
  const startScan = async () => {
    if (scanBusy || !accessKey()) return;
    const t0 = Date.now();
    setSheet("");
    setJob({ mode: "scan", phase: "starting", msg: "Starting a scan…", t0 });
    try {
      const r = await ghApi("/actions/workflows/" + GH_WORKFLOW + "/dispatches", { method: "POST", body: JSON.stringify({ ref: "main", inputs: { new_names: "20" } }) });
      if (r.status === 401 || r.status === 403 || r.status === 404) { askRunOnGitHub(t0); return; }
      if (!r.ok && r.status !== 204) { setJob({ mode: "scan", phase: "error", msg: "GitHub returned " + r.status + ". Try again in a minute, or start the scan on GitHub.", t0 }); return; }
      setJob({ mode: "scan", phase: "queued", msg: "Scan started. Waiting for GitHub to pick it up…", t0 });
      let runId: number | null = null;
      if (r.status === 200) { try { const j = await r.json(); runId = j.workflow_run_id || null; } catch (e) { runId = null; } }
      if (!runId) {
        const run = await findRun(t0, GH_REPO);
        runId = run ? run.id : null;
      }
      if (!runId) { setJob({ mode: "scan", phase: "error", msg: "Started, but couldn’t find the run. Open GitHub or tap Refresh in a couple of minutes.", t0 }); return; }
      await followScan(runId, t0);
    } catch (e) {
      askRunOnGitHub(t0);
    }
  };
  const onScanClick = () => {
    if (busy) return;
    if (hasKey) startScan();
    else setSheet(sheet === "scan" ? "" : "scan");
  };
  const saveKey = () => {
    const v = keyText.trim();
    if (!v) return;
    try { window.localStorage.setItem(KEY_LS, v); } catch (e) { /* ignore */ }
    setKeyText("");
    setHasKey(true);
  };
  useEffect(() => {
    if (!hasKey) return;
    let cancelled = false;
    (async () => {
      try {
        for (const st of ["in_progress", "queued"]) {
          const r = await ghApi("/actions/runs?status=" + st + "&event=workflow_dispatch&per_page=1");
          if (!r.ok || cancelled) return;
          const run = ((await r.json()).workflow_runs || [])[0];
          if (run) {
            const t0 = Date.parse(run.run_started_at || run.created_at);
            setJob({ mode: "scan", phase: st, msg: "A scan is already running…", t0, url: run.html_url });
            followScan(run.id, t0);
            return;
          }
        }
      } catch (e) { /* offline or no key access */ }
    })();
    return () => { cancelled = true; };
  }, [hasKey]);
  const jobBusy = !!job && (job.phase === "starting" || job.phase === "queued" || job.phase === "in_progress" || job.phase === "loading");
  const elapsed = job && jobBusy ? Math.max(0, (Date.now() - job.t0) / 1000) : 0;
  const expect = job && job.mode === "scan" ? SCAN_EXPECT_SECS : 8;
  const pct = job && jobBusy ? (job.phase === "loading" && job.mode === "scan" ? 100 : Math.min(95, Math.round((elapsed / expect) * 100))) : 0;

  const followCaps = (DATA.following && DATA.following.cappers) || [];
  const trialW = followCaps.reduce((a: number, c: FollowCapper) => a + (c.w || 0), 0);
  const trialL = followCaps.reduce((a: number, c: FollowCapper) => a + (c.l || 0), 0);
  const trialN = trialW + trialL;
  const followedN = followCaps.length;
  const db = (DATA.source && DATA.source.db) || {};
  const dbActive = db.active != null ? db.active : (DATA.cappers || []).length;
  const changeTab = (t: "coming" | "following" | "ranked" | "cappers" | "scorecard") => { setTab(t); setFilter("all"); };
  const rankedN = useMemo(() => rankedPicks(todayGames(games, now)).length, [games, now, tick]);
  const tabMeta: { value: "coming" | "following" | "ranked" | "cappers" | "scorecard"; label: string; count?: number; icon: ReactNode; title: string; caption: string }[] = [
    { value: "ranked", label: "Ranked Picks", count: rankedN, icon: <IconTrophy />, title: "Ranked Picks", caption: "$1,000+ singles and combos · best to worst · today in PT, after 7pm + tomorrow" },
    { value: "coming", label: "Coming Up", count: comingN, icon: <IconList />, title: "Coming Up", caption: "$1,000+ singles and combos, soonest first · live first" },
    { value: "cappers", label: "Best Cappers", count: followedN, icon: <IconUsers />, title: "Best Cappers", caption: "Persistent good-only database (target 100) · rechecked every 5 minutes · official profit and closed record" },
    { value: "scorecard", label: "Scorecard", icon: <IconChart />, title: "Scorecard", caption: "Yesterday’s scanner picks · W–L and flat $1" },
  ];
  const active = tabMeta.find((t) => t.value === tab) || tabMeta[0];
  const pills = tab === "coming" || tab === "ranked"
    ? [{ id: "all", label: "All" }, { id: "live", label: "Live" }, { id: "upcoming", label: "Upcoming" }]
    : tab === "following"
    ? [{ id: "all", label: "All" }, { id: "graded", label: "Graded" }, { id: "open", label: "Open picks" }]
    : tab === "scorecard"
    ? []
    : [{ id: "all", label: "All" }, { id: "wl", label: "With a W–L" }, { id: "open", label: "Open picks" }];
  const compactBtn: React.CSSProperties = { minHeight: 36, padding: "0 14px", borderRadius: 10, fontWeight: 800, fontSize: 13, fontFamily: "inherit", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, textDecoration: "none", boxSizing: "border-box", touchAction: "manipulation", whiteSpace: "nowrap" };
  const iconBtn: React.CSSProperties = { ...compactBtn, width: 36, padding: 0, flex: "0 0 36px" };
  return (
    <div style={{ minHeight: "100vh", background: PAGE, color: NAVY, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
      <style>{`
        @keyframes ks-spin{to{transform:rotate(360deg)}}
        .ks-wrap{max-width:1100px;margin:0 auto;padding:20px 20px 48px}
        .ks-hero{position:relative;overflow:hidden;border-radius:24px;background:${NAVY_DEEP};color:#fff;padding:22px 24px 20px;box-shadow:0 0 80px rgba(91,33,182,0.22),0 18px 40px rgba(17,8,31,0.28)}
        .ks-hero::before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,0.045) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.045) 1px,transparent 1px);background-size:28px 28px;mask-image:radial-gradient(ellipse at 30% 0%,#000 0%,transparent 70%);pointer-events:none}
        .ks-hero::after{content:"";position:absolute;width:280px;height:280px;right:-60px;top:-80px;background:radial-gradient(circle,rgba(91,33,182,0.45),transparent 70%);pointer-events:none}
        .ks-hero-row{position:relative;z-index:1;display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
        .ks-hero-actions{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex:0 0 auto}
        .ks-hero-btns{display:flex;align-items:center;gap:8px}
        .ks-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0 0}
        .ks-tabs{display:flex;flex-wrap:nowrap;gap:6px;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none;background:${NAVY};border-radius:16px;padding:6px;margin:16px 0 0}
        .ks-tabs::-webkit-scrollbar{display:none}
        .ks-body{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;align-items:start;margin-top:18px}
        .ks-side{display:flex;flex-direction:column;gap:12px;position:sticky;top:16px}
        .ks-side-card{background:${NAVY};color:#fff;border-radius:16px;padding:14px 16px;box-shadow:0 10px 24px rgba(17,8,31,0.12)}
        .ks-filters{display:flex;flex-wrap:wrap;align-items:center;gap:8px;background:#fff;border:1px solid #DDD6FE;border-radius:14px;padding:8px 10px;margin:0 0 14px}
        .ks-search{flex:1 1 180px;display:flex;align-items:center;gap:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:0 10px;min-height:38px;color:#64748B}
        .ks-search input{border:0;background:transparent;outline:none;width:100%;font:650 15px/1.2 inherit;color:${NAVY};padding:8px 0}
        @media (max-width: 800px){
          .ks-wrap{padding:12px 12px 36px}
          .ks-hero{padding:16px 16px 14px;border-radius:20px}
          .ks-hero-row{flex-direction:column}
          .ks-hero-actions{align-items:stretch;width:100%}
          .ks-hero-btns{justify-content:flex-start}
          .ks-stats{grid-template-columns:1fr 1fr}
          .ks-body{grid-template-columns:1fr;margin-top:14px}
          .ks-side{position:static}
        }
      `}</style>
      <div className="ks-wrap">
        <header className="ks-hero" data-header-actions="1">
          <div className="ks-hero-row">
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 700, color: "#C4B5FD" }}>
                <IconCalendar />
                <span>{formatLongDatePt()}</span>
              </div>
              <h1 style={{ fontSize: 34, fontWeight: 900, letterSpacing: "-0.03em", margin: "8px 0 0", lineHeight: 1.1 }}>Kalshi Scanner</h1>
              <div style={{ fontSize: 15, fontWeight: 600, color: "#94A3B8", marginTop: 6 }}>Kalshi whale picks, best first — public books and trade tape.</div>
              <div data-min-stake="1" style={{ display: "inline-block", marginTop: 8, padding: "4px 10px", borderRadius: 999, background: "rgba(21,128,61,0.2)", border: "1px solid rgba(134,239,172,0.45)", color: "#BBF7D0", fontSize: 13, fontWeight: 800 }}>$1,000+ singles and combos</div>
            </div>
            <div className="ks-hero-actions">
              <div className="ks-hero-btns">
                <button type="button" data-refresh-btn="1" onClick={onRefresh} disabled={refreshing} aria-busy={refreshing} aria-label="Refresh latest scan data" title="Reload the latest published data" style={{ ...iconBtn, border: "1.5px solid rgba(196,181,253,0.55)", background: "rgba(255,255,255,0.06)", color: "#FFFFFF", opacity: refreshing ? 0.85 : 1 }}>
                  {refreshing ? <span data-spinner="1" aria-hidden="true" style={{ width: 14, height: 14, border: "2px solid #DDD6FE", borderTopColor: "#FFFFFF", borderRadius: "50%", display: "inline-block", animation: "ks-spin 0.7s linear infinite" }} /> : <IconRefresh />}
                </button>
                <button type="button" data-scan-btn="1" onClick={onScanClick} disabled={scanBusy} aria-label={hasKey ? "Start a Kalshi scan" : "Open scan options"} title={hasKey ? "Starts a scan on GitHub (~2 min), then this page updates" : "Opens scan options. You can start a scan on GitHub, or save a key on this device."} style={{ ...compactBtn, border: "0", background: "#C4B5FD", color: NAVY_DEEP, opacity: scanBusy ? 0.85 : 1 }}>
                  <IconBolt />
                  {scanBusy ? "Scanning…" : "Run Scan"}
                </button>
              </div>
              <div style={{ fontSize: 12, fontWeight: 650, color: "#DDD6FE", textAlign: "right" }}>
                <div data-data-updated="1" style={{ fontWeight: 800, color: "#FFFFFF" }}>{"Updated " + (DATA.followCheckedAt || DATA.scannedAt || "—")}</div>
                {DATA.followCheckedAt && DATA.scannedAt ? <div data-last-full-scan="1">{"Full scan " + DATA.scannedAt}</div> : null}
                {updatedAt ? <div data-updated-at="1">{"Refreshed " + updatedAt}</div> : null}
                {refreshErr ? <div data-refresh-err="1" style={{ color: "#FECACA" }}>{refreshErr}</div> : null}
              </div>
            </div>
          </div>
          {job ? (
            <div data-job-status={job.phase} style={{ position: "relative", zIndex: 1, marginTop: 12, borderRadius: 14, padding: 12, background: job.phase === "error" ? "rgba(185,28,28,0.45)" : "rgba(0,0,0,0.28)", fontSize: 13, lineHeight: "19px", color: "#FFFFFF" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontWeight: 800 }}><span>{job.msg}</span>{jobBusy ? <span style={{ fontVariantNumeric: "tabular-nums" }}>{mmss(elapsed)}</span> : null}</div>
              {jobBusy ? <div style={{ marginTop: 8, height: 6, borderRadius: 999, background: "rgba(255,255,255,0.25)", overflow: "hidden" }}><div style={{ width: pct + "%", height: "100%", background: "#FFFFFF", transition: "width 1s linear" }} /></div> : null}
              {scanBusy ? <div style={{ marginTop: 6, color: "rgba(255,255,255,0.85)" }}>{"Scans take about 2 minutes. You can leave this page open, or come back later and tap Refresh."}</div> : null}
              {job.phase === "needs_github" ? (
                <a href={SCAN_WORKFLOW_URL} target="_blank" rel="noopener noreferrer" style={{ ...compactBtn, marginTop: 10, border: "1.5px solid #C4B5FD", background: BLUE_BRIGHT, color: "#FFFFFF" }}>Run scan on GitHub ↗</a>
              ) : job.url ? (
                <a href={job.url} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", marginTop: 6, color: "#FFFFFF", fontWeight: 700 }}>View run on GitHub ↗</a>
              ) : job.phase === "error" ? (
                <a href={SCAN_WORKFLOW_URL} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", marginTop: 6, color: "#FFFFFF", fontWeight: 700 }}>Run scan on GitHub ↗</a>
              ) : null}
              {!busy ? <button type="button" onClick={() => setJob(null)} style={{ marginLeft: 12, marginTop: 6, background: "transparent", border: "none", color: "#FFFFFF", textDecoration: "underline", fontSize: 13, padding: 0, cursor: "pointer" }}>Dismiss</button> : null}
            </div>
          ) : null}
          {sheet === "scan" ? (
            <div data-scan-sheet="1" style={{ position: "relative", zIndex: 1, marginTop: 12, borderRadius: 14, padding: 12, background: "rgba(0,0,0,0.28)", fontSize: 13, lineHeight: "19px", color: "#FFFFFF" }}>
              <div style={{ fontWeight: 800, fontSize: 14 }}>Start a scan</div>
              <div style={{ marginTop: 4, color: "rgba(255,255,255,0.9)" }}>{"Runs on GitHub (~2 min) with 20 new names, then tap Refresh. Hourly scans at :20 still run on their own."}</div>
              <a href={SCAN_WORKFLOW_URL} target="_blank" rel="noopener noreferrer" style={{ ...compactBtn, marginTop: 10, border: "1.5px solid #C4B5FD", background: BLUE_BRIGHT, color: "#FFFFFF" }}>Open GitHub to run the workflow</a>
              <div style={{ marginTop: 12, color: "rgba(255,255,255,0.9)" }}>{"Optional: save a fine-grained GitHub token on this device only (Actions access on this repo) to start scans from the button, like the whale scanner. The token is never stored in the public site."}</div>
              <input value={keyText} onChange={(ev) => setKeyText(ev.target.value)} placeholder="github_pat_…" autoComplete="off" style={{ marginTop: 8, width: "100%", boxSizing: "border-box", minHeight: 44, borderRadius: 12, border: "none", padding: "0 12px", fontSize: 16 }} />
              <button type="button" onClick={saveKey} disabled={!keyText.trim()} style={{ ...compactBtn, marginTop: 8, width: "100%", border: "0", background: keyText.trim() ? "#FFFFFF" : "rgba(255,255,255,0.5)", color: BLUE_INK }}>Save key on this device</button>
            </div>
          ) : null}
        </header>

        <div className="ks-stats">
          <DashStat label="Open picks" value={String(comingN)} sub="$1,000+ singles and combos" color={BLUE_BRIGHT} icon={<IconList />} />
          <DashStat label="Best Cappers" value={followedN + "/" + ((capperDatabase().target) || TARGET_FOLLOW)} sub={followedN < ((capperDatabase().target) || TARGET_FOLLOW) ? "good-only (true count)" : "good-only database"} color="#8B5CF6" icon={<IconUsers />} />
          <DashStat label="Cappers in database" value={String(dbActive)} sub={(db.queue != null ? db.queue + " in queue" : "visible sports books")} color="#6366F1" icon={<IconStack />} />
          <DashStat label="Trial record" value={trialN ? (trialW + "–" + trialL) : "—"} sub={trialN ? (((DATA.following && DATA.following.graded) || trialN) + " graded") : "No settled sports W–L yet"} color={trialN ? (trialW > trialL ? GREEN : trialW < trialL ? RED : AMBER) : "#64748B"} icon={<IconChart />} />
        </div>

        <div data-tab-bar="1" className="ks-tabs">
          {tabMeta.map((t) => {
            const on = tab === t.value;
            return (
              <button key={t.value} type="button" onClick={() => changeTab(t.value)} style={{ flex: "0 0 auto", display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 14px", borderRadius: 999, border: "0", background: on ? BLUE : "transparent", color: on ? "#FFFFFF" : "#DDD6FE", fontWeight: 800, fontSize: 14, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap", touchAction: "manipulation" }}>
                {t.icon}
                {t.label}
                {t.count != null ? <span style={{ display: "inline-block", marginLeft: 2, padding: "1px 7px", borderRadius: 999, background: on ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.08)", color: on ? "#FFFFFF" : "#C4B5FD", fontSize: 12 }}>{t.count}</span> : null}
              </button>
            );
          })}
        </div>

        <div className="ks-body">
          <div>
            <div style={{ margin: "0 0 10px" }}>
              <h2 style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-0.03em", margin: 0 }}>{active.title}</h2>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#64748B", marginTop: 4 }}>{active.caption}</div>
            </div>
            {pills.length ? <div className="ks-filters">
              {pills.map((p) => {
                const on = filter === p.id;
                return (
                  <button key={p.id} type="button" onClick={() => setFilter(p.id)} style={{ padding: "6px 12px", borderRadius: 999, border: on ? "0" : "1.5px solid #DDD6FE", background: on ? BLUE : "#FFFFFF", color: on ? "#FFFFFF" : BLUE_INK, fontWeight: 800, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>{p.label}</button>
                );
              })}
              <label className="ks-search">
                <IconSearch />
                <input type="search" value={query} onChange={(ev) => setQuery(ev.target.value)} placeholder="Search cappers or games" aria-label="Search cappers or games" />
              </label>
            </div> : null}
            {tab === "coming" ? <ComingUpTab games={games} now={now} query={query} filter={filter} /> : null}
            {tab === "following" ? <FollowingTab now={now} query={query} filter={filter} /> : null}
            {tab === "ranked" ? <RankedTab games={games} now={now} query={query} filter={filter} /> : null}
            {tab === "cappers" ? <CappersTab now={now} query={query} filter={filter} /> : null}
            {tab === "scorecard" ? <ScorecardTab /> : null}
            <p style={{ margin: "16px 0 0", fontSize: 13, fontWeight: 650, color: "#64748B" }}>Public Kalshi leaderboards, profiles, and the sports trade tape. Records are never invented.</p>
            <details data-how-it-works="1" style={{ marginTop: 16, padding: "8px 0", fontSize: 13, color: "#475569" }}>
              <summary style={{ cursor: "pointer", fontWeight: 800, color: BLUE, listStyle: "none" }}>How it works</summary>
              <p style={{ margin: "8px 0 0", lineHeight: "19px" }}>Public Kalshi leaderboards, profiles, and the sports trade tape. Records are never invented.</p>
              <p style={{ margin: "8px 0 0", lineHeight: "19px" }}>{(DATA.source && DATA.source.note) || "Kalshi public profiles, leaderboards, and the public sports trade tape. Records and tape profit are never invented."}</p>
              <p style={{ margin: "8px 0 0", lineHeight: "19px" }}>{"Refreshed " + (cov.activeRefreshed || 0) + " active · reviewed " + (cov.queueReviewed || 0) + " in queue · new " + (cov.queuedNew || 0) + " · rejected hidden " + (cov.hiddenRejected || 0) + " · MM " + (cov.mmDropped || 0) + " · no sports " + (cov.noSportsRejected || 0) + ". Kalshi period used: " + ((DATA.source && DATA.source.periodUsed) || "monthly") + "."}</p>
            </details>
          </div>
          <aside className="ks-side">
            <div className="ks-side-card" data-data-sources="1">
              <div style={{ fontSize: 14, fontWeight: 850, marginBottom: 4 }}>Data sources</div>
              <StatusRow label="Kalshi markets" status="Public" tone="public" />
              <StatusRow label="Public trades" status="Public tape" tone="ok" />
              <StatusRow label="Social leaderboard" status={"Public ranks"} tone="public" />
              <StatusRow label="Capper books" status={String(dbActive) + " visible"} tone="ok" />
            </div>
            <div className="ks-side-card" data-scan-status="1">
              <div style={{ fontSize: 14, fontWeight: 850, marginBottom: 4 }}>Scan status</div>
              <StatusRow label="Last scan" status={DATA.scannedAt || "—"} tone="ok" />
              {DATA.followCheckedAt ? <StatusRow label="Followed books" status={DATA.followCheckedAt} tone="public" /> : null}
              <StatusRow label="Next hourly scan" status={nextScheduledPt()} tone="public" />
              <StatusRow label="Best Cappers" status={String(followedN)} tone={followedN ? "ok" : "muted"} />
              <div data-capper-db="1" style={{ marginTop: 10, fontSize: 12, fontWeight: 650, color: "#94A3B8" }}>
                {"Capper db: " + (dbActive) + " active" + (db.queue != null ? " · " + db.queue + " to check" : "") + (db.rejected != null ? " · " + db.rejected + " rejected" : "")}
              </div>
            </div>
            <div className="ks-side-card" data-scan-history="1">
              <div style={{ fontSize: 14, fontWeight: 850, marginBottom: 4 }}>Scan history</div>
              <div style={{ fontSize: 12, fontWeight: 650, color: "#94A3B8", marginBottom: 6 }}>Last {(DATA.scanHistory || []).length} scans · kept about 48 (~two days of hourly runs)</div>
              <div style={{ maxHeight: 280, overflowY: "auto" }}>
                {(DATA.scanHistory || []).length === 0 ? <div style={{ fontSize: 13, color: "#94A3B8" }}>No history yet.</div> : (DATA.scanHistory || []).map((h: ScanHist) => (
                  <div key={h.ts} data-scan-hist={h.ts} style={{ padding: "8px 0", borderBottom: "1px solid rgba(148,163,184,0.16)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                      <span style={{ fontSize: 13, fontWeight: 800, color: "#E2E8F0" }}>{h.at || "—"}</span>
                      <span style={{ fontSize: 13, fontWeight: 800, color: "#7DD3FC" }}>{(h.openPicks || 0) + " open"}</span>
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 650, color: "#94A3B8", marginTop: 2 }}>
                      {(h.followed != null ? h.followed + "/" + (h.target || 40) + " followed" : "") + (h.names ? " · " + h.names + " names" : "")}
                    </div>
                    {h.newFollows && h.newFollows.length ? <div style={{ fontSize: 12, fontWeight: 700, color: "#4ADE80", marginTop: 2 }}>{"+" + h.newFollows.join(", ")}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
