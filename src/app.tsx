import React, { useEffect, useMemo, useState, type ReactNode } from "react";

const NAVY = "#0B1F33";
const NAVY_DEEP = "#071422";
const BLUE = "#1D4ED8";
const BLUE_BRIGHT = "#2563EB";
const BLUE_SOFT = "#DBEAFE";
const BLUE_INK = "#1E3A8A";
const PAGE = "#F0F7FF";
const GREEN = "#15803D";
const RED = "#B91C1C";
const AMBER = "#B45309";
const CARD_BUDGET = 40;
const CARD_MIN = 10;
const CARD_MAX = 15;
const ELITE_MIN_BETS = 10;
const FRESH_SECS = 3 * 3600;
const FRESH_MIN = 500;
const DECIDED_PX = 0.97;
const LIVE_HOURS: Record<string, number> = { NFL: 4, CFB: 4, NCAAF: 4, MLB: 3.5, ATP: 3.5, WTA: 3.5, TENNIS: 3.5, UFC: 6, MMA: 6, BOXING: 6, CBB: 2.75, NCAAB: 2.75, NCAAMB: 2.75, NBA: 3, NHL: 3, CS2: 3.5, DOTA2: 3.5, LOL: 3.5, VAL: 3.5, ESPORTS: 3.5 };
const liveSecsFor = (league?: string | null): number => Math.round(3600 * (LIVE_HOURS[(league || "").toUpperCase()] || 3));
const BT_ORDER = ["Moneyline", "Spread", "Totals", "Both teams to score", "Player props", "Other"];

interface WL { w: number; l: number; n?: number }
interface KalshiView { backing?: string; marketTitle?: string; outcome?: string; yesNo: "Yes" | "No" | null; price: number | null; ticker: string | null }
interface Backer { name: string; cost: number; avg?: number | null; line: string; rec?: WL | null; lastTs?: number | null; tier?: string }
interface Pick { key: string; ticker: string; eventTicker?: string; mid: string; bt: string; big: string; sub: string; view: KalshiView; backers: Backer[]; total: number; tags: string[]; slip?: number | null; startTs: number; state: string }
interface Game { id: string; game: string; league: string; startTs: number; start: string; live: boolean; state: string; picks: Pick[] }
interface Capper { nickname: string; profileUrl?: string; tier: string; pinned?: boolean; tag?: string; ranks?: Record<string, number>; pnl?: number | null; weeklyPnl?: number | null; monthlyPnl?: number | null; ageDays?: number | null; graded?: { n: number; w: number; l: number; roi: number | null; profit: number; sample?: string } | null; recordLine: string; pickCount: number }
interface SideCmp { verdict: "this" | "other" | null; thisBest: WL; oppBest: WL; thisName: string; oppName: string }
interface FollowPick { ticker: string; eventTicker?: string; game: string; backing?: string; label?: string; yesNo: "Yes" | "No" | string; entry?: number | null; price?: number | null; cost?: number | null; contracts?: number | null; startTs: number; state?: string; league?: string; bt?: string; nickname: string; recordLine?: string; tier?: string; marketTitle?: string; contractTitle?: string; lastTs?: number | null; slip?: number | null }
interface FollowCapper { nickname: string; w: number; l: number; p?: number; n: number; hitPct: number | null; open: number; hidden?: boolean }
interface Following { startedAt?: string; startedTs?: number; cappers?: FollowCapper[]; picks?: FollowPick[]; recorded?: number; graded?: number }
interface Data { scannedAt: string; ts: number; source?: { note?: string; periodUsed?: string; coverage?: any; db?: { active?: number; queue?: number; rejected?: number; pinned?: number } }; cappers?: Capper[]; games?: Game[]; following?: Following }

let DATA: Data = ((window as any).__DATA || { scannedAt: "", ts: 0, cappers: [], games: [] }) as Data;
const SCAN_WORKFLOW_URL = "https://github.com/nfm0984-png/kalshi-scanner/actions/workflows/scanner.yml";
const GH_OWNER = "nfm0984-png";
const GH_REPO = "kalshi-scanner";
const GH_WORKFLOW = "scanner.yml";
// Device-local only. Never baked into the public site, config.js, or the repo.
const KEY_LS = "kalshi-scanner-gh-key";
const SCAN_EXPECT_SECS = 150;
function accessKey(): string {
  try { const v = window.localStorage.getItem(KEY_LS); if (v) return v.trim(); } catch (e) { /* ignore */ }
  return "";
}
function ghApi(path: string, init?: { method?: string; body?: string }): Promise<Response> {
  const key = accessKey();
  const h: Record<string, string> = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  if (key) h.Authorization = "Bearer " + key;
  if (init && init.body) h["Content-Type"] = "application/json";
  return fetch("https://api.github.com/repos/" + GH_OWNER + "/" + GH_REPO + path, { method: (init && init.method) || "GET", body: init && init.body, headers: h, cache: "no-store" });
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const mmss = (sec: number): string => Math.floor(sec / 60) + ":" + String(Math.floor(sec % 60)).padStart(2, "0");
interface Job { mode: "scan" | "refresh"; phase: string; msg: string; t0: number; url?: string }

function formatNowPt(ms = Date.now()): string {
  return new Date(ms).toLocaleString("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" }) + " PT";
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
async function fetchLatestData(): Promise<Data> {
  const r = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return await r.json();
}

const money = (n: number): string => (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const kMoney = (n: number): string => {
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(a >= 1e7 ? 1 : 2).replace(/\.0$/, "") + "M";
  if (a >= 1000) return s + "$" + (a >= 10000 ? (a / 1000).toFixed(1) + "k" : (a / 1000).toFixed(a >= 1000 && a < 10000 ? 1 : 0) + "k").replace(/\.0k$/, "k");
  return s + "$" + Math.round(a).toLocaleString("en-US");
};
const cents = (px: number | null | undefined): string => {
  if (px == null || px <= 0) return "—";
  const x = Math.round((1 / Math.min(px, 1)) * 10) / 10;
  return x.toFixed(1).replace(/\.0$/, "") + "x";
};
const payoutOf = (p: Pick): number => (p.view.price ? Math.round((1 / Math.min(p.view.price, 1)) * 10) / 10 : 99);
const ptTime = (ts: number): string => new Date(ts * 1000).toLocaleString("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PT";
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
const kalshiUrlOf = (ticker: string | null | undefined): string | null => {
  const ev = eventTickerOf(ticker || null);
  return ev ? "https://kalshi.com/markets/" + ev.toLowerCase() : null;
};

function Chip(props: { bg: string; color: string; children: ReactNode }) {
  return <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: props.bg, color: props.color, fontSize: 11, fontWeight: 850 }}>{props.children}</span>;
}
function Text(props: { children: ReactNode }) {
  return <p style={{ fontSize: 14, lineHeight: "20px", color: "#334155", margin: "0 2px 12px" }}>{props.children}</p>;
}
function EmptyState(props: { title: string; body: string }) {
  return (
    <div style={{ padding: "18px 14px", borderRadius: 16, border: "1.5px dashed #93C5FD", background: "#FFFFFF", margin: "8px 0 12px" }}>
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
    <div style={{ flex: "1 1 72px", minWidth: 72, background: props.bg || "#F0F7FF", borderRadius: 14, padding: "10px 8px 9px", textAlign: "center", boxShadow: "0 1px 0 rgba(255,255,255,0.7) inset" }}>
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
        <circle cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke="#BFDBFE" strokeWidth="6" />
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
  const accent = props.live ? "linear-gradient(90deg,#DC2626,#F97316)" : (props.followed ? "linear-gradient(90deg," + BLUE + "," + BLUE_BRIGHT + ")" : "linear-gradient(90deg," + BLUE + ",#38BDF8)");
  return (
    <div data-capper-shell={props.followed ? "followed" : "1"} style={{ borderRadius: 20, border: "1.5px solid #BFDBFE", background: "#FFFFFF", boxShadow: "0 6px 18px rgba(11,31,51,0.10)", overflow: "hidden", marginBottom: 14, fontFamily: "inherit" }}>
      <div style={{ height: 6, background: accent }} />
      <div style={{ padding: "12px 14px 14px" }}>{props.children}</div>
    </div>
  );
}
function isFollowedCapper(c: Capper): boolean {
  return !!(c.pinned || c.tier === "My 40" || c.tier === "Top 10" || c.tier === "Following" || c.tag === "My 40");
}
function tierColors(tier: string): { bg: string; fg: string } {
  if (tier === "My 40" || tier === "Top 10" || tier === "Following") return { bg: "#FEF3C7", fg: "#92400E" };
  if (tier === "Core") return { bg: BLUE_SOFT, fg: BLUE_INK };
  if (tier === "Top 50") return { bg: "#E0E7FF", fg: "#3730A3" };
  return { bg: "#F1F5F9", fg: "#334155" };
}
function TierChip(props: { tier: string }) {
  if (!props.tier) return null;
  const t = tierColors(props.tier);
  return <span data-tier={props.tier} style={{ display: "inline-block", padding: "0 8px", borderRadius: 999, background: t.bg, color: t.fg, border: "1.5px solid " + t.fg, fontSize: 11, fontWeight: 850, lineHeight: "18px" }}>{props.tier}</span>;
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
  const tone = settled ? recTone(g!.w, g!.l) : { fg: NAVY, bg: "#F0F7FF" };
  const tiles: ReactNode[] = [
    <StatTile key="rec" label="Record" value={settled ? (g!.w + "–" + g!.l) : "—"} color={tone.fg} bg={tone.bg} />,
    <StatTile key="wr" label="Win rate" value={settled ? pctText(g!.w / (g!.w + g!.l)) : "—"} color={tone.fg} bg={tone.bg} />,
  ];
  if (g && g.profit != null) tiles.push(<StatTile key="prof" label="Graded profit" value={(g.profit >= 0 ? "+" : "") + kMoney(g.profit)} color={g.profit >= 0 ? GREEN : RED} bg={g.profit >= 0 ? "#DCFCE7" : "#FEE2E2"} sub={g.roi != null ? ((g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI") : undefined} />);
  if (props.c.pnl != null) tiles.push(<StatTile key="pnl" label="All-time P&L" value={(props.c.pnl >= 0 ? "+" : "") + kMoney(props.c.pnl)} color={props.c.pnl >= 0 ? GREEN : RED} bg={props.c.pnl >= 0 ? "#DCFCE7" : "#FEE2E2"} />);
  if (props.c.monthlyPnl != null) tiles.push(<StatTile key="mo" label="Monthly P&L" value={(props.c.monthlyPnl >= 0 ? "+" : "") + kMoney(props.c.monthlyPnl)} color={props.c.monthlyPnl >= 0 ? GREEN : RED} />);
  if (props.c.weeklyPnl != null) tiles.push(<StatTile key="wk" label="Weekly P&L" value={(props.c.weeklyPnl >= 0 ? "+" : "") + kMoney(props.c.weeklyPnl)} color={props.c.weeklyPnl >= 0 ? GREEN : RED} />);
  return <div data-record-strip="1" style={{ display: "flex", gap: 8, margin: "10px 0 0", flexWrap: "wrap" }}>{tiles}</div>;
}
function sportsHeadline(c?: Capper | null): { text: string; color: string } {
  const g = gradedWL(c);
  if (g && (g.w + g.l) > 0) {
    const t = recTone(g.w, g.l);
    return { text: g.w + "–" + g.l + " · " + pctText(g.w / (g.w + g.l)) + (g.roi != null ? " · " + (g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI" : ""), color: t.fg };
  }
  if (c && c.pnl != null) return { text: (c.pnl >= 0 ? "+" : "") + kMoney(c.pnl) + " all-time · no settled sports W-L yet", color: c.pnl >= 0 ? GREEN : RED };
  return { text: "No graded sports record yet", color: "#64748B" };
}
function BackerRow(props: { b: Backer; now: number }) {
  const b = props.b;
  const cap = capperOf(b.name);
  const fromBacker = b.rec && (b.rec.w + b.rec.l) > 0 ? { w: b.rec.w, l: b.rec.l, roi: (cap && cap.graded && cap.graded.roi != null ? cap.graded.roi : null) as number | null } : null;
  const fromDb = gradedWL(cap);
  const g = fromBacker || (fromDb && (fromDb.w + fromDb.l) > 0 ? { w: fromDb.w, l: fromDb.l, roi: fromDb.roi } : null);
  return (
    <div data-backer-row={b.name} data-ucard-rec={b.name} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 8 }}>
      <Face name={b.name} size={28} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {g ? <RecordPill w={g.w} l={g.l} roi={g.roi} /> : <RecordPill w={0} l={0} />}
          {b.tier ? <TierChip tier={b.tier} /> : null}
        </div>
        <div style={{ fontSize: 13, lineHeight: "18px", fontWeight: 750, color: NAVY, marginTop: 3, overflowWrap: "anywhere" }}>
          {b.name + " · " + money(b.cost) + (b.avg != null ? " at " + cents(b.avg) : "") + (b.lastTs ? " · bought " + ago(b.lastTs, props.now) : "")}
        </div>
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
    <div data-capper-pick={p.key} style={{ marginTop: 10, padding: "10px 0 0", borderTop: "1px solid #DBEAFE" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
        {game.league ? <Chip bg={BLUE_SOFT} color={BLUE_INK}>{game.league}</Chip> : null}
        <Chip bg="#F8FAFC" color="#334155">{(live ? "Started " : "Starts ") + (p.startTs || game.startTs ? ptTime(p.startTs || game.startTs) : "—")}</Chip>
      </div>
      <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 850, color: NAVY, marginTop: 6, overflowWrap: "anywhere" }}>{game.game}</div>
      <div style={{ fontSize: 15, fontWeight: 800, color: BLUE_INK, marginTop: 2, overflowWrap: "anywhere" }}>{p.big}{p.view.yesNo ? " · " + p.view.yesNo : ""}</div>
      {mine ? <div style={{ marginTop: 4, display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}><span style={{ fontSize: 20, lineHeight: "24px", fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{money(mine.cost)}</span><span style={{ fontSize: 13, fontWeight: 700, color: "#64748B" }}>{"on Kalshi" + (mine.avg != null ? " · entry " + cents(mine.avg) : "")}</span></div> : null}
      <FreshPricePills p={p} now={now} />
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={p.view} /></div>
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
    <div data-follow-pick={p.ticker} style={{ marginTop: 10, padding: "10px 0 0", borderTop: "1px solid #DBEAFE" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
        {p.league ? <Chip bg={BLUE_SOFT} color={BLUE_INK}>{p.league}</Chip> : null}
        {p.bt ? <Chip bg="#F8FAFC" color="#334155">{p.bt}</Chip> : null}
        <Chip bg="#F8FAFC" color="#334155">{p.startTs ? ((live ? "Started " : "Starts ") + ptTime(p.startTs)) : "—"}</Chip>
      </div>
      <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 850, color: NAVY, marginTop: 6, overflowWrap: "anywhere" }}>{p.game}</div>
      <div style={{ fontSize: 15, fontWeight: 800, color: BLUE_INK, marginTop: 2, overflowWrap: "anywhere" }}>{(p.backing || p.label || p.game) + " · " + (p.yesNo || "")}</div>
      <div style={{ marginTop: 4, display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        {p.cost != null && p.cost > 0 ? <span style={{ fontSize: 20, lineHeight: "24px", fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{kMoney(p.cost)}</span> : null}
        <span style={{ fontSize: 13, fontWeight: 700, color: "#64748B" }}>{"on Kalshi" + (p.price != null ? " · pays " + cents(p.price) : "") + (p.entry != null ? " · entry " + cents(p.entry) : "")}</span>
      </div>
      {fresh === "fresh" || fresh === "hold" ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
          {fresh === "fresh" ? pill("#DCFCE7", "#15803D", "Fresh", p.lastTs ? "bought " + ago(p.lastTs as number, props.now) : null) : null}
          {fresh === "hold" ? pill("#F3F4F6", "#4B5563", "Hold", "no buys in 24h") : null}
        </div>
      ) : null}
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={view} /></div>
    </div>
  );
}


function gameOver(g: Game, now: number): boolean {
  if (g.startTs && now >= g.startTs + liveSecsFor(g.league)) return true;
  if (/^(UFC|MMA|BOXING)$/i.test(g.league || "")) return false;
  if (g.startTs && g.startTs <= now) {
    return (g.picks || []).some((p: Pick) => p.bt === "Moneyline" && p.view.price != null && (p.view.price >= DECIDED_PX || (p.view.price <= 1 - DECIDED_PX && p.view.yesNo === "No")));
  }
  return false;
}
function openGames(now: number): Game[] {
  return (DATA.games || []).filter((g: Game) => !gameOver(g, now) && (!g.startTs || g.startTs <= now + 24 * 3600));
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
/** Laplace / add-one shrink toward 50%: (W+1)/(W+L+2). Weight grows with settled bets. */
const sideStrength = (rec: WL): number => (rec.w + 1) / ((rec.w + rec.l) + 2);
const NET_CLOSE = 0.08; // 8 percentage points — "small net margin"
const netPts = (net: number): number => Math.round(net * 100);
const netText = (net: number): string => {
  const pts = netPts(net);
  return "Net " + (pts > 0 ? "+" + pts : String(pts));
};
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
interface NetInfo { net: number; own: number; opp: number; ownRec: WL; oppRec: WL; ownN: number; oppN: number; contested: boolean }
function netOf(p: Pick, game: Game): NetInfo {
  const own = uniqueSide(p.backers);
  const seen: Record<string, boolean> = {};
  const oppBackers: Backer[] = [];
  oppositionPicks(p, game).forEach((q: Pick) => q.backers.forEach((b: Backer) => {
    if (seen[b.name]) return;
    seen[b.name] = true;
    oppBackers.push(b);
  }));
  const opp = uniqueSide(oppBackers);
  const ownS = sideStrength(own.rec);
  const oppS = opp.n ? sideStrength(opp.rec) : 0;
  const net = ownS - oppS;
  const oppNBets = opp.rec.w + opp.rec.l;
  const oppRate = oppNBets ? opp.rec.w / oppNBets : 0;
  const strongOpp = oppRate >= 0.60 && oppNBets >= ELITE_MIN_BETS;
  const close = opp.n > 0 && Math.abs(net) < NET_CLOSE;
  return { net, own: ownS, opp: oppS, ownRec: own.rec, oppRec: opp.rec, ownN: own.n, oppN: opp.n, contested: !!(strongOpp || close) };
}
function weakerSide(p: Pick, game: Game): boolean {
  const mine = netOf(p, game).net;
  return oppositionPicks(p, game).some((q: Pick) => netOf(q, game).net > mine + 1e-12);
}
function bestPickFirst(picks: Pick[], game: Game): Pick[] {
  return picks.slice().sort((a: Pick, b: Pick) => {
    const na = netOf(a, game), nb = netOf(b, game);
    return (nb.net - na.net) || (nb.ownRec.w - na.ownRec.w) || (nb.ownN - na.ownN) || ((b.total || 0) - (a.total || 0));
  });
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
  const mine: { r: WL; name: string }[] = [];
  const theirs: { r: WL; name: string }[] = [];
  const seen: Record<string, boolean> = {};
  p.backers.forEach((b: Backer) => { if (b.rec) mine.push({ r: b.rec, name: b.name }); });
  opp.forEach((q: Pick) => q.backers.forEach((b: Backer) => { if (seen[b.name]) return; seen[b.name] = true; if (b.rec) theirs.push({ r: b.rec, name: b.name }); }));
  if (!mine.length || !theirs.length) return null;
  const best = (list: { r: WL; name: string }[]) => list.slice().sort((x, y) => (wlBetter(x.r, y.r) ? -1 : wlBetter(y.r, x.r) ? 1 : 0))[0];
  const tb = best(mine), ob = best(theirs);
  const verdict = wlBetter(ob.r, tb.r) ? "other" : wlBetter(tb.r, ob.r) ? "this" : null;
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
  const url = kalshiUrlOf(v.ticker);
  const col = yes ? GREEN : RED;
  return (
    <div data-on-kalshi="1" style={{ marginTop: 10, padding: "10px 12px", borderRadius: 14, border: "1.5px dashed " + BLUE, background: "#EFF6FF" }}>
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
    return <div data-other-side="1" style={{ marginTop: 10, padding: "9px 12px", borderRadius: 14, background: "#EFF6FF", color: BLUE_INK }}><div style={{ fontSize: 11, fontWeight: 850, letterSpacing: "0.08em", textTransform: "uppercase", color: BLUE }}>Other side</div><div style={{ fontSize: 14, fontWeight: 700, marginTop: 2 }}>No tracked cappers on the other side</div></div>;
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
  const other = c.verdict === "other";
  const col = other ? AMBER : GREEN;
  return (
    <div data-record-flag={c.verdict} style={{ marginTop: 10, padding: "10px 12px", borderRadius: 14, border: "2px solid " + col, background: other ? "#FEF3C7" : "#F0FDF4" }}>
      <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 900, color: col, overflowWrap: "anywhere" }}>{other ? "⚠ Other side: " + c.oppName + " (" + wlText(c.oppBest) + ") is betting against this" : "Better record than other side (" + wlText(c.thisBest) + " vs " + wlText(c.oppBest) + ")"}</div>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#52525B", marginTop: 3 }}>{other ? "Best on this side: " + c.thisName + " (" + wlText(c.thisBest) + ") · " + (wlRate(c.thisBest) * 100).toFixed(1) + "% vs " + (wlRate(c.oppBest) * 100).toFixed(1) + "%" : "Best on this side: " + c.thisName + " (" + wlText(c.thisBest) + "), best on other side: " + c.oppName + " (" + wlText(c.oppBest) + ")"}</div>
    </div>
  );
}
function FreshPricePills(props: { p: Pick; now: number }) {
  const fresh = freshOf(props.p, props.now);
  const slip = slipTierOf(props.p);
  if (!fresh.tag && !slip) return null;
  const pill = (bg: string, fg: string, text: string, sub: string | null, attr: string) => (
    <span data-pill={attr} style={{ display: "inline-flex", alignItems: "baseline", gap: 5, padding: "3px 10px", borderRadius: 999, background: bg, color: fg, border: "1.5px solid " + fg, fontSize: 13, fontWeight: 850 }}>{text}{sub ? <span style={{ fontSize: 11, fontWeight: 700, opacity: 0.85 }}>{sub}</span> : null}</span>
  );
  return (
    <div data-pills="1" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
      {fresh.tag === "fresh" ? pill("#DCFCE7", "#15803D", "Fresh", fresh.ts ? "bought " + ago(fresh.ts, props.now) : null, "fresh") : null}
      {fresh.tag === "hold" ? pill("#F3F4F6", "#4B5563", "Hold", "no buys in 24h", "hold") : null}
      {slip === "good" ? pill("#DCFCE7", "#15803D", "Good price", null, "price-good") : null}
      {slip === "slight" ? pill("#FEF3C7", "#92400E", "Slightly worse", null, "price-slight") : null}
      {slip === "much" ? pill("#FEE2E2", "#B91C1C", "Much worse", null, "price-much") : null}
    </div>
  );
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

function UCard(props: { p: Pick; game: Game; now: number; stake: string; moreRow?: ReactNode; stakeLine?: string; rankNo?: number }) {
  const p = props.p;
  const v = p.view;
  const opp = oppositeOf(p, props.game);
  const cmp = sideCompare(p, props.game);
  const net = netOf(p, props.game);
  const top = p.backers.slice(0, 3);
  const rest = p.backers.slice(3);
  const colorOf = (x: string): string[] => (({ "My 40": ["#FEF3C7", "#92400E"], "Top 10": ["#FEF3C7", "#92400E"], Following: ["#FEF3C7", "#92400E"], Core: ["#DBEAFE", "#1E3A8A"], "Top 50": ["#E0E7FF", "#3730A3"], Board: ["#F1F5F9", "#334155"], Weekly: ["#F1F5F9", "#334155"] } as Record<string, string[]>)[x] || ["#F1F5F9", "#334155"]);
  return (
    <div data-ucard={p.key} data-contested={net.contested ? "1" : "0"} style={{ borderRadius: 18, border: net.contested ? "2px solid #F59E0B" : "1.5px solid #BFDBFE", background: "#FFFFFF", boxShadow: "0 4px 14px rgba(11,31,51,0.08)", overflow: "hidden", marginBottom: 10, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
      <div style={{ padding: "12px 14px 12px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 6 }}>
          {props.rankNo ? <span data-card-no="1" style={{ display: "inline-block", minWidth: 26, textAlign: "center", padding: "2px 8px", borderRadius: 999, background: BLUE, color: "#FFFFFF", fontSize: 13, fontWeight: 900 }}>{"#" + props.rankNo}</span> : null}
          {props.game.live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
          <span style={{ fontSize: 12, fontWeight: 700, color: "#64748B" }}>{props.game.league + " · " + (props.game.startTs ? ptTime(props.game.startTs) : "") + (p.bt ? " · " + p.bt : "")}</span>
        </div>
        <div data-ucard-big="1" style={{ fontSize: 22, lineHeight: "27px", fontWeight: 850, letterSpacing: "-0.01em", overflowWrap: "anywhere", color: NAVY }}>{p.big}</div>
        {p.sub ? <div style={{ fontSize: 14, lineHeight: "19px", fontWeight: 600, color: "#475569", marginTop: 2, overflowWrap: "anywhere" }}>{p.sub}</div> : null}
        <div data-ucard-sum="1" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 10 }}>
          <span data-ucard-total="1" style={{ display: "inline-block", padding: "3px 12px", borderRadius: 12, background: BLUE_BRIGHT, color: "#FFFFFF", fontSize: 28, lineHeight: "34px", fontWeight: 900, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>{kMoney(p.total)}</span>
          <span data-ucard-count="1" style={{ display: "inline-block", padding: "4px 10px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 15, fontWeight: 850 }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s")}</span>
          <span data-net-pill="1" style={{ display: "inline-block", padding: "3px 9px", borderRadius: 999, background: "#F8FAFC", color: "#334155", border: "1px solid #CBD5E1", fontSize: 13, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{netText(net.net)}</span>
          {p.tags.map((x: string) => <span key={x} style={{ display: "inline-block", padding: "3px 9px", borderRadius: 999, background: colorOf(x)[0], color: colorOf(x)[1], fontSize: 13, fontWeight: 850, border: "1.5px solid " + colorOf(x)[1] }}>{x}</span>)}
        </div>
        <FreshPricePills p={p} now={props.now} />
        {props.moreRow}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
          <div style={{ flex: 1 }}><KalshiBuyButton view={v} /></div>
          <div data-k-stake="1" style={{ fontSize: 14, fontWeight: 800, color: GREEN, lineHeight: "17px" }}>{"Stake"}<br />{props.stake}</div>
        </div>
        {props.stakeLine ? <div data-stake-line="1" style={{ marginTop: 6, fontSize: 14, fontWeight: 850, color: GREEN, fontVariantNumeric: "tabular-nums" }}>{props.stakeLine}</div> : null}
        <OnKalshiBox view={v} />
        {top.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
        {net.contested ? <div data-contested-badge="1" style={{ marginTop: 10, padding: "8px 12px", borderRadius: 14, border: "1.5px solid #F59E0B", background: "#FFF7ED", color: "#9A3412", fontSize: 14, fontWeight: 800 }}>{"Contested: " + net.oppN + " capper" + (net.oppN === 1 ? "" : "s") + " " + wlText(net.oppRec) + " against"}</div> : null}
        {cmp && cmp.verdict && opp.length ? <RecordFlag cmp={cmp} /> : null}
        <OtherSide p={p} opp={opp} />
        {rest.length ? (
          <details data-ucard-more="1" style={{ marginTop: 8 }}>
            <summary style={{ cursor: "pointer", fontWeight: 800, fontSize: 14, color: BLUE }}>{"Details · +" + rest.length + " more"}</summary>
            {rest.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
          </details>
        ) : null}
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
    <div data-alt-bet={p.key} data-contested={net.contested ? "1" : "0"} style={{ borderRadius: 14, border: net.contested ? "2px solid #F59E0B" : "1.5px solid #BFDBFE", background: "#FFFFFF", padding: "10px 12px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 18, lineHeight: "22px", fontWeight: 850, overflowWrap: "anywhere", flex: 1, minWidth: 0, color: NAVY }}>{p.big}</div>
        <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 10, background: BLUE_BRIGHT, color: "#FFFFFF", fontSize: 18, fontWeight: 900, fontVariantNumeric: "tabular-nums" }}>{kMoney(p.total)}</span>
      </div>
      {p.sub ? <div style={{ fontSize: 13, fontWeight: 600, color: "#475569", marginTop: 2 }}>{p.sub}</div> : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 6 }}>
        <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 13, fontWeight: 850 }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s")}</span>
        <span data-net-pill="1" style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: "#F8FAFC", color: "#334155", border: "1px solid #CBD5E1", fontSize: 12, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{netText(net.net)}</span>
        {p.tags.map((x: string) => <span key={x} style={{ display: "inline-block", padding: "1px 8px", borderRadius: 999, background: "#F1F5F9", color: "#334155", fontSize: 12, fontWeight: 800, border: "1px solid #94A3B8" }}>{x}</span>)}
      </div>
      <FreshPricePills p={p} now={props.now} />
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={p.view} /></div>
      <OnKalshiBox view={p.view} />
      {p.backers.map((b: Backer) => <BackerRow key={b.name} b={b} now={props.now} />)}
      {net.contested ? <div data-contested-badge="1" style={{ marginTop: 8, padding: "7px 10px", borderRadius: 12, border: "1.5px solid #F59E0B", background: "#FFF7ED", color: "#9A3412", fontSize: 13, fontWeight: 800 }}>{"Contested: " + net.oppN + " capper" + (net.oppN === 1 ? "" : "s") + " " + wlText(net.oppRec) + " against"}</div> : null}
      {cmp && cmp.verdict && opp.length ? <RecordFlag cmp={cmp} /> : null}
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

interface RankedCard { game: Game; rec: WL; cappers: number; net: number; contested: boolean }
function gameRec(g: Game): { rec: WL; cappers: number; net: number; contested: boolean } {
  const main = bestPickFirst(g.picks || [], g)[0];
  if (!main) return { rec: { w: 0, l: 0 }, cappers: 0, net: -1, contested: false };
  const n = netOf(main, g);
  return { rec: n.ownRec, cappers: n.ownN, net: n.net, contested: n.contested };
}
function rankedLists(games: Game[]): { top: RankedCard[]; others: RankedCard[]; small: RankedCard[]; contested: RankedCard[] } {
  const cards = games.map((game: Game) => ({ game, ...gameRec(game) }));
  const cmp = (a: RankedCard, b: RankedCard) => (b.net - a.net) || (b.rec.w - a.rec.w) || (b.cappers - a.cappers) || ((a.game.startTs || 1e12) - (b.game.startTs || 1e12));
  const un = cards.filter((c: RankedCard) => !c.contested);
  const contested = cards.filter((c: RankedCard) => c.contested).sort(cmp);
  const big = un.filter((c: RankedCard) => c.rec.w + c.rec.l >= ELITE_MIN_BETS).sort(cmp);
  const small = un.filter((c: RankedCard) => c.rec.w + c.rec.l < ELITE_MIN_BETS).sort(cmp);
  return { top: big.slice(0, 15), others: big.slice(15), small, contested };
}
interface CardPick { p: Pick; game: Game; n: number; stake: number }
function todayCard(games: Game[], now: number): { picks: CardPick[]; total: number } {
  const L = rankedLists(games);
  const order = L.top.concat(L.others, L.small, L.contested);
  const eligible = (p: Pick, g: Game) => !g.live && g.startTs > now && p.view.price != null && !!p.view.yesNo && payoutOf(p) < 3 && !netOf(p, g).contested && !weakerSide(p, g);
  const warned = (p: Pick, g: Game) => { const c = sideCompare(p, g); return !!(c && c.verdict === "other"); };
  const rows: { p: Pick; game: Game; n: number }[] = [];
  order.forEach((c: RankedCard) => {
    const pick = bestPickFirst(c.game.picks, c.game).filter((p: Pick) => eligible(p, c.game))[0];
    if (pick) rows.push({ p: pick, game: c.game, n: pick.backers.length });
  });
  const chosen: { p: Pick; game: Game; n: number }[] = [];
  const take = (r: { p: Pick; game: Game; n: number }) => { chosen.push(r); };
  rows.forEach((r) => { if (chosen.length < CARD_MAX && payoutOf(r.p) <= 1.8 && !warned(r.p, r.game)) take(r); });
  rows.forEach((r) => { if (chosen.length < CARD_MIN && chosen.indexOf(r) < 0 && !warned(r.p, r.game)) take(r); });
  rows.forEach((r) => { if (chosen.length < CARD_MIN && chosen.indexOf(r) < 0) take(r); });
  const picks: CardPick[] = chosen.map((r) => ({ p: r.p, game: r.game, n: r.n, stake: r.n >= 3 ? 4 : r.n === 2 ? 3 : 2 }));
  let total = picks.reduce((a: number, c: CardPick) => a + c.stake, 0);
  while (total > CARD_BUDGET) {
    let j = -1;
    for (let i = picks.length - 1; i >= 0; i--) { if (picks[i].stake > 2) { j = i; break; } }
    if (j < 0) break;
    picks[j].stake -= 1; total -= 1;
  }
  for (let i = 0; i < picks.length && total < CARD_BUDGET; i++) { if (picks[i].stake < 4) { picks[i].stake += 1; total += 1; } }
  return { picks, total };
}
function TodayCard(props: { games: Game[]; now: number }) {
  const card = todayCard(props.games, props.now);
  const freshN = card.picks.filter((c: CardPick) => freshOf(c.p, props.now).tag === "fresh").length;
  return (
    <div data-today-card="1" style={{ marginBottom: 18 }}>
      <div style={{ borderRadius: 18, background: NAVY, color: "#FFFFFF", padding: "14px 16px", marginBottom: 12 }}>
        <div style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-0.01em" }}>{"Today's $" + CARD_BUDGET + " card"}</div>
        <div data-card-total="1" style={{ fontSize: 16, fontWeight: 800, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{card.picks.length + " picks · $2–4 each · total $" + card.total + " of $" + CARD_BUDGET}</div>
        <div style={{ fontSize: 13, fontWeight: 650, opacity: 0.9, marginTop: 4 }}>{"One pick per game, taken from the Ranked list below (highest net score first). Safer payouts (1.8x or less) first, nothing paying 3x or more, contested picks left off, picks with the amber other-side warning last." + (freshN ? " " + freshN + " fresh." : "")}</div>
      </div>
      {card.picks.length === 0 ? <EmptyState title="No picks fit the card right now" body={"Nothing upcoming pays under 3x with a public Kalshi capper on the same side. The Ranked games are below."} /> : card.picks.map((c: CardPick, i: number) => (
        <UCard key={"card-" + c.p.key} p={c.p} game={c.game} now={props.now} stake={"$" + c.stake} stakeLine={"$" + c.stake + " · total $" + card.total + " of $" + CARD_BUDGET} rankNo={i + 1} />
      ))}
      <div style={{ fontSize: 12, fontWeight: 650, color: "#64748B", margin: "2px 2px 0" }}>{"Suggested stakes only. Nothing is placed for you. No parlays."}</div>
    </div>
  );
}

function ComingUpTab(props: { games: Game[]; now: number }) {
  const live = props.games.filter((g: Game) => g.live).sort((a, b) => (a.startTs || 0) - (b.startTs || 0) || (a.id < b.id ? -1 : 1));
  const up = props.games.filter((g: Game) => !g.live).sort((a, b) => (a.startTs || 1e12) - (b.startTs || 1e12) || (a.id < b.id ? -1 : 1));
  const pickN = props.games.reduce((n: number, g: Game) => n + g.picks.length, 0);
  return (
    <Section heading={"Coming Up · " + pickN} caption={"Soonest start first · already started at the top · starts within 24 hours"}>
      <Text>{"Every open $100+ sports position from Kalshi traders who show their book, grouped by game and sorted by start time. Finished games are removed. Suggested $2–4 a ticket, about $40 a day. No parlays."}</Text>
      <div data-combined-summary="1" style={{ fontSize: 14, fontWeight: 750, color: "#475569", margin: "2px 2px 12px" }}>{pickN + " picks · " + props.games.length + " games · " + live.length + " live"}</div>
      {props.games.length === 0 ? <EmptyState title="No public Kalshi books right now" body={"None of the visible sports traders in the capper db has a $100+ open sports position starting within 24 hours. Most top traders hide their book."} /> : null}
      {live.length ? <div data-live-head="1" style={{ fontSize: 22, fontWeight: 900, margin: "10px 2px 2px", color: NAVY }}>{"Already started (" + live.length + ")"}</div> : null}
      {live.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart />)}
      {up.length ? <div data-all-today="1" style={{ fontSize: 22, fontWeight: 900, margin: "10px 2px 2px", color: NAVY }}>{"Upcoming (" + up.length + ")"}</div> : null}
      {up.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart />)}
    </Section>
  );
}
function RankedTab(props: { games: Game[]; now: number }) {
  const L = rankedLists(props.games);
  const total = L.top.length + L.others.length + L.small.length + L.contested.length;
  const render = (c: RankedCard, i: number) => <GameBlock key={c.game.id} g={c.game} now={props.now} stake="$2–4" rankNo={i + 1} rec={c.rec} cappers={c.cappers} />;
  return (
    <Section heading={"Ranked · " + total} caption={"Games ranked by the main pick’s net score (own side minus opposition) · uncontested first · starts or is live within 24 hours"}>
      <Text>{"Each game is one card. The main pick is the highest-net side — never the weaker side of the same market. Net = own Laplace strength (W+1)/(W+L+2) minus the same for cappers on the other outcome (and the other team’s moneyline). Rank uses that net, then own wins, then own cappers. Record counts, money does not. Contested games (opposition at 60%+ with 10+ bets, or a net under 8 points) sit below uncontested and are left off the $40 card. The amber warning still names a capper on the other side with a better individual record."}</Text>
      <div data-ranked-summary="1" style={{ fontSize: 14, fontWeight: 750, color: "#475569", margin: "2px 2px 8px" }}>{total + " games · " + L.top.length + " in the top list · " + L.contested.length + " contested"}</div>
      {total > 0 ? <TodayCard games={props.games} now={props.now} /> : null}
      {total === 0 ? <EmptyState title="No ranked games right now" body={"No visible Kalshi capper has a $100+ sports pick starting within 24 hours."} /> : null}
      {L.top.length ? <div data-elite-top="1" style={{ fontSize: 22, fontWeight: 900, margin: "4px 2px 4px", color: NAVY }}>{"Top " + L.top.length}</div> : null}
      {L.top.map((c: RankedCard, i: number) => render(c, i))}
      {L.others.length ? <div data-ranked-section="others" style={{ fontSize: 22, fontWeight: 900, margin: "18px 2px 4px", paddingTop: 10, borderTop: "3px solid " + BLUE, color: NAVY }}>{"All other games · " + L.others.length}</div> : null}
      {L.others.map((c: RankedCard, i: number) => render(c, L.top.length + i))}
      {L.small.length ? <div data-ranked-section="small" style={{ fontSize: 22, fontWeight: 900, margin: "18px 2px 4px", paddingTop: 10, borderTop: "3px solid " + BLUE, color: NAVY }}>{"Small sample (under " + ELITE_MIN_BETS + " bets) · " + L.small.length}</div> : null}
      {L.small.length ? <Text>{"The main pick’s own cappers have fewer than 10 settled bets, so these sit below the main lists. They are still sorted by net score, and contested games are in their own section below."}</Text> : null}
      {L.small.map((c: RankedCard, i: number) => render(c, L.top.length + L.others.length + i))}
      {L.contested.length ? <div data-ranked-section="contested" style={{ fontSize: 22, fontWeight: 900, margin: "18px 2px 4px", paddingTop: 10, borderTop: "3px solid #F59E0B", color: NAVY }}>{"Contested · " + L.contested.length}</div> : null}
      {L.contested.length ? <Text>{"Meaningful opposition on the main pick: the other side is at 60%+ with 10+ settled bets, or the net margin is under 8 points. Sorted by net, below every uncontested game. Left off the $40 card."}</Text> : null}
      {L.contested.map((c: RankedCard, i: number) => render(c, L.top.length + L.others.length + L.small.length + i))}
    </Section>
  );
}
function FollowingTab(props: { now: number }) {
  const F = DATA.following || { cappers: [], picks: [], startedAt: "", recorded: 0, graded: 0 };
  const caps = F.cappers || [];
  const picks = (F.picks || []).slice();
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
  return (
    <Section heading={"My 40 · " + picks.length} caption={"Every open traditional-sports pick from followed winning cappers (up to 40) · no dollar minimum · soonest start first, grouped under each capper"}>
      <Text>{"If you like a capper, every open sports pick from their book lands here — singles and sports combos, no $ minimum and no record gate. Only cappers with a winning graded record (W > L) are followed, up to 40. Discovery keeps running every hour even at 40; a followed capper who falls to a losing record is swapped out and stays in Coming Up / Ranked. Esports and finished games are left off. Each pick is recorded once in a copy trial and graded from Kalshi’s official market result after it settles."}</Text>
      <div data-trial-box="1" style={{ borderRadius: 16, border: "1.5px solid #FDE68A", background: "#FFFBEB", padding: "12px 14px", marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 850, letterSpacing: "0.06em", textTransform: "uppercase", color: "#92400E" }}>Copy trial</div>
        <div style={{ fontSize: 16, fontWeight: 850, color: NAVY, marginTop: 2 }}>
          {F.startedAt ? ("Since " + F.startedAt + ((F.recorded || 0) ? " · " + (F.recorded || 0) + " recorded" : "") + ((F.graded || 0) ? " · " + (F.graded || 0) + " graded" : "")) : "Trial starts when the first followed pick is recorded."}
        </div>
        <div data-record-strip="trial" style={{ display: "flex", gap: 8, margin: "10px 0 0", flexWrap: "wrap" }}>
          <StatTile label="Wins" value={String(tw)} color={GREEN} bg="#DCFCE7" />
          <StatTile label="Losses" value={String(tl)} color={RED} bg="#FEE2E2" />
          <StatTile label="Record" value={tn ? (tw + "–" + tl) : "—"} color={trialTone.fg} bg={trialTone.bg} />
          <StatTile label="Hit rate" value={hit == null ? "—" : hit + "%"} color={trialTone.fg} bg={trialTone.bg} />
          <StatTile label="Cappers" value={String(caps.length)} />
          <StatTile label="Open picks" value={String(picks.length)} />
        </div>
        {caps.length === 0 ? <div style={{ fontSize: 14, fontWeight: 650, color: "#57534E", marginTop: 8 }}>{"No followed cappers yet. When followed cappers are seeded, they’ll show up here with a running hit rate."}</div> : null}
      </div>
      {picks.length === 0 && caps.length ? <EmptyState title="No open followed picks right now" body={"Your followed cappers don’t have an open traditional-sports position, or their books are hidden. Finished games drop off; the trial still grades what was already recorded."} /> : null}
      {picks.length === 0 && !caps.length ? <EmptyState title="My 40 is waiting on followed cappers" body={"The followed-capper list is empty. Seed data/cappers_pinned.json or drop /workspace/kalshi-top10-cappers.json and the next scan will fill this tab."} /> : null}
      {ordered.map((c: FollowCapper) => {
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
                  {c.n ? ((c.w + "–" + c.l) + " copy trial" + (trialPct != null ? " · " + trialPct + "% hit" : "")) : "Copy trial · no grades yet"}
                  {c.hidden ? " · book hidden" : ""}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: head.color, marginTop: 2 }}>{settled ? ("Sports tape " + head.text) : head.text}</div>
              </div>
              {trialPct != null ? <WinRing pct={trialPct} /> : (settled ? <WinRing pct={Math.round(100 * g!.w / (g!.w + g!.l))} /> : null)}
              <Chip bg={mine.length ? GREEN : "#F1F5F9"} color={mine.length ? "#FFFFFF" : "#475569"}>{mine.length === 1 ? "1 pick" : mine.length + " picks"}</Chip>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 8 }}>
              <TierChip tier="My 40" />
              {g && g.sample === "small" ? <Chip bg="#FEF3C7" color={AMBER}>Small sample</Chip> : null}
              <RankChips ranks={cap && cap.ranks} />
              {c.open ? <Chip bg={BLUE_BRIGHT} color="#FFFFFF">{c.open} open</Chip> : null}
            </div>
            {cap ? <CapperStatRow c={cap} /> : null}
            {mine.length ? mine.map((fp: FollowPick) => <FollowPickMini key={c.nickname + "|" + fp.ticker + "|" + fp.yesNo} p={fp} now={props.now} />) : <div style={{ fontSize: 13, fontWeight: 650, color: "#64748B", marginTop: 10 }}>No open traditional-sports picks from this capper right now.</div>}
          </CapperShell>
        );
      })}
    </Section>
  );
}
function CappersTab(props: { now: number }) {
  const caps = (DATA.cappers || []).slice();
  const followedN = caps.filter(isFollowedCapper).length;
  const openN = caps.reduce((n: number, c: Capper) => n + (c.pickCount || 0), 0);
  const settledN = caps.filter((c: Capper) => { const g = gradedWL(c); return !!(g && (g.w + g.l) > 0); }).length;
  return (
    <Section heading={"Cappers · " + caps.length} caption={"Visible Sports-leaderboard traders, plus followed My 40 cappers. Hidden books are not listed unless followed. Picks are grouped under each capper."}>
      <Text>{"A capper has to show their bets on Kalshi to appear here, except followed My 40 names, who stay in the db even with a hidden book. My 40 = Noel’s followed list (winning record, never rejected). Core = in both the all-time and monthly top 50. Top 50 = on one of those boards. W-L is reconstructed from their public sports trade tape, not invented. Market makers are left out unless followed. Picks are traditional sports singles and combos only — no esports."}</Text>
      <div data-record-strip="cappers" style={{ display: "flex", gap: 8, margin: "4px 0 14px", flexWrap: "wrap" }}>
        <StatTile label="Cappers" value={String(caps.length)} />
        <StatTile label="Followed" value={String(followedN)} />
        <StatTile label="With a W-L" value={String(settledN)} />
        <StatTile label="Open picks" value={String(openN)} />
      </div>
      {caps.length === 0 ? <EmptyState title="No visible cappers right now" body={"Almost every name on Kalshi's Sports leaderboard hides their book."} /> : caps.map((c: Capper, i: number) => {
        const g = gradedWL(c);
        const settled = !!(g && (g.w + g.l) > 0);
        const head = sportsHeadline(c);
        const picks = openPicksFor(c.nickname, props.now);
        const hasLive = picks.some((x) => !!x.game.live || !!(x.p.startTs && x.p.startTs <= props.now));
        const wr = settled ? Math.round(100 * g!.w / (g!.w + g!.l)) : null;
        return (
          <CapperShell key={c.nickname} live={hasLive} followed={isFollowedCapper(c)}>
            <div data-capper={c.nickname} style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <div style={{ fontSize: 18, fontWeight: 850, color: BLUE, minWidth: 28 }}>{"#" + (i + 1)}</div>
              <Face name={c.nickname} size={44} />
              <div style={{ flex: 1, minWidth: 0 }}>
                {c.profileUrl ? (
                  <a href={c.profileUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 18, fontWeight: 850, color: NAVY, textDecoration: "none", overflowWrap: "anywhere" }}>{c.nickname} ↗</a>
                ) : (
                  <div style={{ fontSize: 18, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}</div>
                )}
                <div style={{ fontSize: 13, fontWeight: 800, color: head.color, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{head.text}</div>
              </div>
              {wr != null ? <WinRing pct={wr} /> : null}
              <Chip bg={picks.length ? GREEN : "#F1F5F9"} color={picks.length ? "#FFFFFF" : "#475569"}>{picks.length === 1 ? "1 pick" : picks.length + " picks"}</Chip>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 8 }}>
              {c.tier ? <TierChip tier={c.tier} /> : null}
              {g && g.sample === "small" ? <Chip bg="#FEF3C7" color={AMBER}>Small sample</Chip> : (settled ? <Chip bg={GREEN} color="#FFFFFF">{g!.n}+ graded</Chip> : <Chip bg="#F1F5F9" color="#475569">No sports W-L yet</Chip>)}
              <RankChips ranks={c.ranks} />
              {c.ageDays != null ? <Chip bg="#F8FAFC" color="#334155">{c.ageDays + "d on Kalshi"}</Chip> : null}
            </div>
            <CapperStatRow c={c} />
            {picks.length ? picks.map((x) => <CapperPickMini key={c.nickname + "|" + x.p.key} p={x.p} game={x.game} now={props.now} backerName={c.nickname} />) : <div style={{ fontSize: 13, fontWeight: 650, color: "#64748B", marginTop: 10 }}>{c.pickCount ? "Open picks are under the $100 Coming Up window, or already started and dropped from this list." : "No open $100+ pick in the window."}</div>}
          </CapperShell>
        );
      })}
    </Section>
  );
}

export default function App() {
  const [tab, setTab] = useState<"coming" | "following" | "ranked" | "cappers">(() => {
    try {
      const t = new URLSearchParams(window.location.search).get("tab");
      if (t === "coming" || t === "following" || t === "ranked" || t === "cappers") return t;
    } catch (e) {}
    return "coming";
  });
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Math.round(Date.now() / 1000));
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [clock, setClock] = useState(0);
  const [sheet, setSheet] = useState<"" | "scan">("");
  const [hasKey, setHasKey] = useState<boolean>(() => !!accessKey());
  const [keyText, setKeyText] = useState("");
  const games = useMemo(() => openGames(now), [now, tick]);
  const comingN = games.reduce((n: number, g: Game) => n + g.picks.length, 0);
  const cov = (DATA.source && DATA.source.coverage) || {};
  const followN = ((DATA.following && DATA.following.picks) || []).length;
  const tabs = [
    { value: "coming" as const, label: "Coming Up", count: comingN },
    { value: "following" as const, label: "My 40", count: followN },
    { value: "ranked" as const, label: "Ranked", count: games.length },
    { value: "cappers" as const, label: "Cappers", count: (DATA.cappers || []).length },
  ];
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
      setJob({ mode: "refresh", phase: "done", msg: "Updated " + formatNowPt(), t0 });
    }).catch(() => {
      setRefreshErr("Couldn't refresh. Try again.");
      setJob({ mode: "refresh", phase: "error", msg: "Couldn't refresh. Try again.", t0 });
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
  const findRun = async (t0: number): Promise<number | null> => {
    for (let i = 0; i < 12; i++) {
      await sleep(4000);
      try {
        const r = await ghApi("/actions/runs?event=workflow_dispatch&per_page=5");
        if (r.ok) {
          const j = await r.json();
          const run = (j.workflow_runs || []).find((x: { created_at?: string; id?: number }) => Date.parse(x.created_at || "") >= t0 - 90000);
          if (run && run.id) return run.id;
        }
      } catch (e) { /* retry */ }
    }
    return null;
  };
  const startScan = async () => {
    if (busy || !accessKey()) return;
    const t0 = Date.now();
    setSheet("");
    setJob({ mode: "scan", phase: "starting", msg: "Starting a scan (20 new names)…", t0 });
    try {
      const r = await ghApi("/actions/workflows/" + GH_WORKFLOW + "/dispatches", { method: "POST", body: JSON.stringify({ ref: "main", inputs: { new_names: "20" } }) });
      if (r.status === 401 || r.status === 403 || r.status === 404) { setJob({ mode: "scan", phase: "error", msg: "GitHub rejected the access key (" + r.status + "). It may be expired or missing Actions access. You can still start a scan on GitHub.", t0 }); return; }
      if (!r.ok && r.status !== 204) { setJob({ mode: "scan", phase: "error", msg: "GitHub returned " + r.status + ". Try again in a minute, or start the scan on GitHub.", t0 }); return; }
      let runId: number | null = null;
      if (r.status === 200) { try { const j = await r.json(); runId = j.workflow_run_id || null; } catch (e) { runId = null; } }
      if (!runId) runId = await findRun(t0);
      if (!runId) { setJob({ mode: "scan", phase: "error", msg: "Started, but couldn’t find the run. Open GitHub or tap Refresh in a couple of minutes.", t0 }); return; }
      await followScan(runId, t0);
    } catch (e) {
      setJob({ mode: "scan", phase: "error", msg: "Couldn't reach GitHub. Open the Actions page to start a scan, then tap Refresh.", t0 });
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
  const elapsed = job && scanBusy ? Math.max(0, (Date.now() - job.t0) / 1000) : 0;
  const pct = job && scanBusy ? (job.phase === "loading" ? 100 : Math.min(95, Math.round((elapsed / SCAN_EXPECT_SECS) * 100))) : 0;
  const btnBase: React.CSSProperties = { flex: "1 1 140px", minHeight: 44, padding: "10px 14px", borderRadius: 12, fontWeight: 850, fontSize: 15, fontFamily: "inherit", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, textDecoration: "none", boxSizing: "border-box" };
  return (
    <div style={{ minHeight: "100vh", background: PAGE, color: NAVY, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
      <header style={{ background: NAVY_DEEP, color: "#FFFFFF", padding: "16px 16px 18px" }}>
        <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "#93C5FD" }}>Kalshi · Whale signals</div>
        <h1 style={{ fontSize: 28, fontWeight: 900, letterSpacing: "-0.03em", margin: "4px 0 0" }}>Kalshi Scanner</h1>
        <div style={{ fontSize: 14, fontWeight: 650, color: "#BFDBFE", marginTop: 4 }}>Kalshi whale picks, best first. Scanned {DATA.scannedAt || "—" }.</div>
        <div data-header-actions="1" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
          <button type="button" data-refresh-btn="1" onClick={onRefresh} disabled={busy} aria-busy={refreshing} aria-label="Refresh latest scan data" style={{ ...btnBase, border: "0", background: BLUE_BRIGHT, color: "#FFFFFF", opacity: refreshing ? 0.85 : 1 }}>
            {refreshing ? <span data-spinner="1" aria-hidden="true" style={{ width: 16, height: 16, border: "2px solid #BFDBFE", borderTopColor: "#FFFFFF", borderRadius: "50%", display: "inline-block", animation: "ks-spin 0.7s linear infinite" }} /> : null}
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" data-scan-btn="1" onClick={onScanClick} disabled={scanBusy} aria-label={hasKey ? "Start a Kalshi scan" : "Open scan options"} title={hasKey ? "Starts a scan on GitHub (~2 min), then this page updates" : "Opens scan options. You can start a scan on GitHub, or save a key on this device."} style={{ ...btnBase, border: "1.5px solid #93C5FD", background: "transparent", color: "#FFFFFF", opacity: scanBusy ? 0.85 : 1 }}>
            {scanBusy ? "Scanning…" : "Scan"}
          </button>
        </div>
        <div style={{ fontSize: 12, fontWeight: 650, color: "#BFDBFE", marginTop: 8, lineHeight: "18px" }}>
          {updatedAt ? <div data-updated-at="1">{"Updated " + updatedAt}</div> : null}
          {refreshErr ? <div data-refresh-err="1" style={{ color: "#FECACA" }}>{refreshErr}</div> : null}
          <div>{"Last scan: " + (DATA.scannedAt || "—") + " · Next scheduled: " + nextScheduledPt()}</div>
          {!job && !sheet ? <div style={{ opacity: 0.9 }}>{"Refresh loads the latest data on this page. Scan starts a ~2 min GitHub run" + (hasKey ? ", then this page updates when it finishes." : " — tap Scan to open options.")}</div> : null}
        </div>
        {job ? (
          <div data-job-status={job.phase} style={{ marginTop: 10, borderRadius: 14, padding: 12, background: job.phase === "error" ? "rgba(185,28,28,0.45)" : "rgba(0,0,0,0.28)", fontSize: 13, lineHeight: "19px", color: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontWeight: 800 }}><span>{job.msg}</span>{scanBusy ? <span style={{ fontVariantNumeric: "tabular-nums" }}>{mmss(elapsed)}</span> : null}</div>
            {scanBusy ? <div style={{ marginTop: 8, height: 6, borderRadius: 999, background: "rgba(255,255,255,0.25)", overflow: "hidden" }}><div style={{ width: pct + "%", height: "100%", background: "#FFFFFF", transition: "width 1s linear" }} /></div> : null}
            {scanBusy ? <div style={{ marginTop: 6, color: "rgba(255,255,255,0.85)" }}>{"Scans take about 2 minutes. You can leave this page open, or come back later and tap Refresh."}</div> : null}
            {job.url ? <a href={job.url} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", marginTop: 6, color: "#FFFFFF", fontWeight: 700 }}>View run on GitHub ↗</a> : null}
            {!busy ? <button type="button" onClick={() => setJob(null)} style={{ marginLeft: job.url ? 12 : 0, marginTop: 6, background: "transparent", border: "none", color: "#FFFFFF", textDecoration: "underline", fontSize: 13, padding: 0, cursor: "pointer" }}>Dismiss</button> : null}
          </div>
        ) : null}
        {sheet === "scan" ? (
          <div data-scan-sheet="1" style={{ marginTop: 10, borderRadius: 14, padding: 12, background: "rgba(0,0,0,0.28)", fontSize: 13, lineHeight: "19px", color: "#FFFFFF" }}>
            <div style={{ fontWeight: 800, fontSize: 14 }}>Start a scan</div>
            <div style={{ marginTop: 4, color: "rgba(255,255,255,0.9)" }}>{"Runs on GitHub (~2 min) with 20 new names, then tap Refresh. Hourly scans at :20 still run on their own."}</div>
            <a href={SCAN_WORKFLOW_URL} target="_blank" rel="noopener noreferrer" style={{ ...btnBase, marginTop: 10, border: "1.5px solid #93C5FD", background: BLUE_BRIGHT, color: "#FFFFFF" }}>Open GitHub to run the workflow</a>
            <div style={{ marginTop: 12, color: "rgba(255,255,255,0.9)" }}>{"Optional: save a fine-grained GitHub token on this device only (Actions access on this repo) to start scans from the button, like the whale scanner. The token is never stored in the public site."}</div>
            <input value={keyText} onChange={(ev) => setKeyText(ev.target.value)} placeholder="github_pat_…" autoComplete="off" style={{ marginTop: 8, width: "100%", boxSizing: "border-box", minHeight: 44, borderRadius: 12, border: "none", padding: "0 12px", fontSize: 16 }} />
            <button type="button" onClick={saveKey} disabled={!keyText.trim()} style={{ ...btnBase, marginTop: 8, width: "100%", border: "0", background: keyText.trim() ? "#FFFFFF" : "rgba(255,255,255,0.5)", color: BLUE_INK }}>Save key on this device</button>
          </div>
        ) : null}
      </header>
      <style>{"@keyframes ks-spin{to{transform:rotate(360deg)}}"}</style>
      <div style={{ maxWidth: 430, margin: "0 auto", padding: "12px 12px 40px" }}>
        <div data-tab-bar="1" style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "4px 0 14px" }}>
          {tabs.map((t) => {
            const on = tab === t.value;
            return (
              <button key={t.value} type="button" onClick={() => setTab(t.value)} style={{ padding: "8px 12px", borderRadius: 999, border: on ? "0" : "1.5px solid #93C5FD", background: on ? BLUE : "#FFFFFF", color: on ? "#FFFFFF" : BLUE_INK, fontWeight: 850, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
                {t.label}{" "}
                <span style={{ display: "inline-block", marginLeft: 4, padding: "0 7px", borderRadius: 999, background: on ? "#FFFFFF" : BLUE_SOFT, color: on ? BLUE : BLUE_INK, fontSize: 12 }}>{t.count}</span>
              </button>
            );
          })}
        </div>
        {tab === "coming" ? <ComingUpTab games={games} now={now} /> : null}
        {tab === "following" ? <FollowingTab now={now} /> : null}
        {tab === "ranked" ? <RankedTab games={games} now={now} /> : null}
        {tab === "cappers" ? <CappersTab now={now} /> : null}
        <details style={{ marginTop: 18, padding: "10px 12px", borderRadius: 14, background: "#FFFFFF", border: "1px solid #BFDBFE" }}>
          <summary style={{ cursor: "pointer", fontWeight: 800, color: BLUE }}>How this is sourced</summary>
          <p style={{ fontSize: 13, lineHeight: "19px", color: "#475569" }}>{(DATA.source && DATA.source.note) || "Kalshi Sports leaderboard, public profiles, and the public trade tape."}</p>
          <p style={{ fontSize: 13, lineHeight: "19px", color: "#475569" }}>{"Refreshed " + (cov.activeRefreshed || 0) + " active · reviewed " + (cov.queueReviewed || 0) + " in queue · new " + (cov.queuedNew || 0) + " · rejected hidden " + (cov.hiddenRejected || 0) + " · MM " + (cov.mmDropped || 0) + " · no sports " + (cov.noSportsRejected || 0) + ". Kalshi period used: " + ((DATA.source && DATA.source.periodUsed) || "monthly") + "."}</p>
        </details>
        <div data-capper-db="1" style={{ marginTop: 12, fontSize: 11, color: "#64748B", textAlign: "center" }}>
          {"Capper db: " + (((DATA.source && DATA.source.db && DATA.source.db.active) || 0)) + " active · " + (((DATA.source && DATA.source.db && DATA.source.db.queue) || 0)) + " to check · " + (((DATA.source && DATA.source.db && DATA.source.db.rejected) || 0)) + " rejected" + ((DATA.source && DATA.source.db && DATA.source.db.pinned) ? " · " + DATA.source.db.pinned + " followed (target 40)" : "")}
        </div>
      </div>
    </div>
  );
}
