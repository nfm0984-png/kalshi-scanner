import React, { useMemo, useState, type ReactNode } from "react";

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
interface FollowPick { ticker: string; eventTicker?: string; game: string; backing?: string; label?: string; yesNo: "Yes" | "No" | string; entry?: number | null; price?: number | null; cost?: number | null; contracts?: number | null; startTs: number; state?: string; league?: string; bt?: string; nickname: string; recordLine?: string; tier?: string; marketTitle?: string; contractTitle?: string }
interface FollowCapper { nickname: string; w: number; l: number; p?: number; n: number; hitPct: number | null; open: number; hidden?: boolean }
interface Following { startedAt?: string; startedTs?: number; cappers?: FollowCapper[]; picks?: FollowPick[]; recorded?: number; graded?: number }
interface Data { scannedAt: string; ts: number; source?: { note?: string; periodUsed?: string; coverage?: any; db?: { active?: number; queue?: number; rejected?: number; pinned?: number } }; cappers?: Capper[]; games?: Game[]; following?: Following }

const DATA: Data = ((window as any).__DATA || { scannedAt: "", ts: 0, cappers: [], games: [] }) as Data;

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
        {top.map((b: Backer) => <div key={b.name} data-ucard-rec={b.name} style={{ fontSize: 14, lineHeight: "20px", fontWeight: 650, color: "#475569", marginTop: 2, overflowWrap: "anywhere" }}>{b.line}</div>)}
        {net.contested ? <div data-contested-badge="1" style={{ marginTop: 10, padding: "8px 12px", borderRadius: 14, border: "1.5px solid #F59E0B", background: "#FFF7ED", color: "#9A3412", fontSize: 14, fontWeight: 800 }}>{"Contested: " + net.oppN + " capper" + (net.oppN === 1 ? "" : "s") + " " + wlText(net.oppRec) + " against"}</div> : null}
        {cmp && cmp.verdict && opp.length ? <RecordFlag cmp={cmp} /> : null}
        <OtherSide p={p} opp={opp} />
        <details data-ucard-more="1" style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", fontWeight: 800, fontSize: 14, color: BLUE }}>{rest.length ? "Details · +" + rest.length + " more" : "Details"}</summary>
          {p.backers.map((b: Backer, i: number) => (
            <div key={b.name} style={{ borderTop: "1px solid #E2E8F0", marginTop: 8, paddingTop: 8 }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 15, fontWeight: 850, overflowWrap: "anywhere", color: NAVY }}>{b.name}</span>
                <span><span style={{ fontSize: 16, fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>{money(b.cost)}</span><span style={{ fontSize: 13, fontWeight: 700, color: "#64748B" }}>{b.avg != null ? " @ " + Math.round(b.avg * 100) + "¢ entry" : ""}</span></span>
              </div>
              {i >= 3 ? <div style={{ fontSize: 13, fontWeight: 650, color: "#475569" }}>{b.line}</div> : null}
            </div>
          ))}
        </details>
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
      {p.backers.map((b: Backer) => <div key={b.name} style={{ fontSize: 13, lineHeight: "19px", fontWeight: 650, color: "#475569", marginTop: 2, overflowWrap: "anywhere" }}>{b.line}</div>)}
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
  const picks = (F.picks || []).slice().sort((a: FollowPick, b: FollowPick) => {
    const al = !!(a.startTs && a.startTs <= props.now), bl = !!(b.startTs && b.startTs <= props.now);
    return (al === bl ? 0 : al ? -1 : 1) || ((a.startTs || 1e12) - (b.startTs || 1e12)) || (a.nickname || "").localeCompare(b.nickname || "") || (a.ticker || "").localeCompare(b.ticker || "");
  });
  const tw = caps.reduce((a: number, c: FollowCapper) => a + (c.w || 0), 0);
  const tl = caps.reduce((a: number, c: FollowCapper) => a + (c.l || 0), 0);
  const tn = tw + tl;
  const hit = tn ? Math.round((1000 * tw) / tn) / 10 : null;
  return (
    <Section heading={"My 40 · " + picks.length} caption={"Every open traditional-sports pick from followed winning cappers (up to 40) · no dollar minimum · soonest start first"}>
      <Text>{"If you like a capper, every open sports pick from their book lands here — singles and sports combos, no $ minimum and no record gate. Only cappers with a winning graded record (W > L) are followed, up to 40. Discovery keeps running every hour even at 40; a followed capper who falls to a losing record is swapped out and stays in Coming Up / Ranked. Esports and finished games are left off. Each pick is recorded once in a copy trial and graded from Kalshi’s official market result after it settles."}</Text>
      <div data-trial-box="1" style={{ borderRadius: 16, border: "1.5px solid #FDE68A", background: "#FFFBEB", padding: "12px 14px", marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 850, letterSpacing: "0.06em", textTransform: "uppercase", color: "#92400E" }}>Copy trial</div>
        <div style={{ fontSize: 16, fontWeight: 850, color: NAVY, marginTop: 2 }}>
          {F.startedAt ? ("Since " + F.startedAt + (tn ? " · " + tw + "-" + tl + " · " + hit + "% hit" : " · no settled picks yet") + ((F.recorded || 0) ? " · " + (F.recorded || 0) + " recorded" : "")) : "Trial starts when the first followed pick is recorded."}
        </div>
        {caps.length === 0 ? <div style={{ fontSize: 14, fontWeight: 650, color: "#57534E", marginTop: 6 }}>{"No followed cappers yet. When followed cappers are seeded, they’ll show up here with a running hit rate."}</div> : null}
        {caps.map((c: FollowCapper) => (
          <div key={c.nickname} data-trial-capper={c.nickname} style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", borderTop: "1px solid #FDE68A", marginTop: 8, paddingTop: 8 }}>
            <div style={{ fontSize: 15, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}{c.hidden ? " · book hidden" : ""}</div>
            <div style={{ fontSize: 14, fontWeight: 800, color: "#57534E", fontVariantNumeric: "tabular-nums" }}>
              {(c.n ? (c.w + "-" + c.l + " · " + c.hitPct + "% hit") : "0-0 · no grades yet") + " · " + c.open + " open"}
            </div>
          </div>
        ))}
      </div>
      {picks.length === 0 && caps.length ? <EmptyState title="No open followed picks right now" body={"Your followed cappers don’t have an open traditional-sports position, or their books are hidden. Finished games drop off; the trial still grades what was already recorded."} /> : null}
      {picks.length === 0 && !caps.length ? <EmptyState title="My 40 is waiting on followed cappers" body={"The followed-capper list is empty. Seed data/cappers_pinned.json or drop /workspace/kalshi-top10-cappers.json and the next scan will fill this tab."} /> : null}
      {picks.map((p: FollowPick) => {
        const live = !!(p.startTs && p.startTs <= props.now);
        const view = { backing: p.backing || p.label || p.game, marketTitle: p.marketTitle || p.game, outcome: p.backing || p.label, yesNo: (p.yesNo === "No" ? "No" : "Yes") as "Yes" | "No", price: p.price ?? null, ticker: p.ticker };
        return (
          <div key={p.nickname + "|" + p.ticker + "|" + p.yesNo} data-follow-pick={p.ticker} style={{ borderRadius: 16, border: "1.5px solid #BFDBFE", background: "#FFFFFF", padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 4, fontSize: 13, fontWeight: 700, color: "#64748B" }}>
              {live ? <Chip bg={RED} color="#FFFFFF">LIVE</Chip> : null}
              <span>{(p.league || "Sports") + (p.bt ? " · " + p.bt : "") + (p.startTs ? " · " + (live ? "Started " : "Starts ") + ptTime(p.startTs) : "")}</span>
            </div>
            <div style={{ fontSize: 18, lineHeight: "23px", fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{p.game}</div>
            <div style={{ fontSize: 16, lineHeight: "21px", fontWeight: 800, color: BLUE_INK, marginTop: 2, overflowWrap: "anywhere" }}>{(p.backing || p.label || p.game) + " · " + (p.yesNo || "")}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 8 }}>
              <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: "#FEF3C7", color: "#92400E", fontSize: 12, fontWeight: 850, border: "1.5px solid #92400E" }}>{p.nickname}</span>
              {p.price != null ? <span style={{ fontSize: 14, fontWeight: 850, color: NAVY, fontVariantNumeric: "tabular-nums" }}>{cents(p.price)}</span> : null}
              {p.cost != null && p.cost > 0 ? <span style={{ fontSize: 13, fontWeight: 700, color: "#475569" }}>{kMoney(p.cost) + " in the book"}</span> : null}
            </div>
            <div style={{ marginTop: 8 }}><KalshiBuyButton view={view} /></div>
          </div>
        );
      })}
    </Section>
  );
}
function CappersTab(props: { now: number }) {
  const caps = DATA.cappers || [];
  return (
    <Section heading={"Cappers · " + caps.length} caption={"Visible Sports-leaderboard traders, plus followed My 40 cappers. Hidden books are not listed unless followed."}>
      <Text>{"A capper has to show their bets on Kalshi to appear here, except followed My 40 names, who stay in the db even with a hidden book. My 40 = Noel’s followed list (winning record, never rejected). Core = in both the all-time and monthly top 50. Top 50 = on one of those boards. W-L is reconstructed from their public sports trade tape, not invented. Market makers are left out unless followed. Picks are traditional sports singles and combos only — no esports."}</Text>
      {caps.length === 0 ? <EmptyState title="No visible cappers right now" body={"Almost every name on Kalshi's Sports leaderboard hides their book."} /> : caps.map((c: Capper) => {
        const g = c.graded;
        return (
          <div key={c.nickname} data-capper={c.nickname} style={{ borderRadius: 16, border: "1.5px solid #BFDBFE", background: "#FFFFFF", padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
              <div style={{ fontSize: 17, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}</div>
              <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: (c.pinned || c.tier === "Top 10" || c.tier === "My 40" || c.tier === "Following") ? "#FEF3C7" : BLUE_SOFT, color: (c.pinned || c.tier === "Top 10" || c.tier === "My 40" || c.tier === "Following") ? "#92400E" : BLUE_INK, fontSize: 12, fontWeight: 850, border: (c.pinned || c.tier === "Top 10" || c.tier === "My 40" || c.tier === "Following") ? "1.5px solid #92400E" : "0" }}>{c.tier}</span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#475569", marginTop: 4 }}>
              {g && g.n ? (g.w + "-" + g.l + " · " + pctText(g.w / Math.max(1, g.w + g.l)) + (g.roi != null ? " · " + (g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI" : "") + (g.sample === "small" ? " · small sample" : "")) : "No graded sports record yet"}
              {c.pnl != null ? " · " + (c.pnl >= 0 ? "+" : "") + kMoney(c.pnl) + " all-time" : ""}
            </div>
            <div style={{ fontSize: 12, fontWeight: 650, color: "#64748B", marginTop: 2 }}>
              {(c.ranks && c.ranks.all_time ? "All-time #" + c.ranks.all_time : "") + (c.ranks && c.ranks.monthly ? " · Monthly #" + c.ranks.monthly : "") + (c.ranks && c.ranks.weekly ? " · Weekly #" + c.ranks.weekly : "") + (c.pickCount ? " · " + c.pickCount + " open pick" + (c.pickCount === 1 ? "" : "s") : " · no open $100+ pick in the window")}
            </div>
            {c.profileUrl ? <a href={c.profileUrl} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 800, color: BLUE, textDecoration: "none" }}>Kalshi profile ↗</a> : null}
          </div>
        );
      })}
    </Section>
  );
}

export default function App() {
  const [tab, setTab] = useState<"coming" | "following" | "ranked" | "cappers">("coming");
  const now = Math.round(Date.now() / 1000);
  const games = useMemo(() => openGames(now), [now]);
  const comingN = games.reduce((n: number, g: Game) => n + g.picks.length, 0);
  const cov = (DATA.source && DATA.source.coverage) || {};
  const followN = ((DATA.following && DATA.following.picks) || []).length;
  const tabs = [
    { value: "coming" as const, label: "Coming Up", count: comingN },
    { value: "following" as const, label: "My 40", count: followN },
    { value: "ranked" as const, label: "Ranked", count: games.length },
    { value: "cappers" as const, label: "Cappers", count: (DATA.cappers || []).length },
  ];
  return (
    <div style={{ minHeight: "100vh", background: PAGE, color: NAVY, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
      <header style={{ background: NAVY_DEEP, color: "#FFFFFF", padding: "16px 16px 18px" }}>
        <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "#93C5FD" }}>Kalshi · Whale signals</div>
        <h1 style={{ fontSize: 28, fontWeight: 900, letterSpacing: "-0.03em", margin: "4px 0 0" }}>Kalshi Scanner</h1>
        <div style={{ fontSize: 14, fontWeight: 650, color: "#BFDBFE", marginTop: 4 }}>Kalshi whale picks, best first. Scanned {DATA.scannedAt || "—" }.</div>
      </header>
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
