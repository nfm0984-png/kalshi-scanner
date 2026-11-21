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
interface Capper { nickname: string; profileUrl?: string; tier: string; ranks?: Record<string, number>; pnl?: number | null; weeklyPnl?: number | null; monthlyPnl?: number | null; ageDays?: number | null; graded?: { n: number; w: number; l: number; roi: number | null; profit: number; sample?: string } | null; recordLine: string; pickCount: number }
interface SideCmp { verdict: "this" | "other" | null; thisBest: WL; oppBest: WL; thisName: string; oppName: string }
interface Data { scannedAt: string; ts: number; source?: { note?: string; periodUsed?: string; coverage?: any }; cappers?: Capper[]; games?: Game[] }

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
function pickRec(p: Pick): WL {
  let w = 0, l = 0;
  p.backers.forEach((b: Backer) => { if (b.rec) { w += b.rec.w; l += b.rec.l; } });
  return { w, l };
}
function bestPickFirst(picks: Pick[]): Pick[] {
  const sample = (r: WL): number => (r.w + r.l >= ELITE_MIN_BETS ? 1 : 0);
  return picks.slice().sort((a: Pick, b: Pick) => {
    const ra = pickRec(a), rb = pickRec(b);
    return (sample(rb) - sample(ra)) || (wlRate(rb) - wlRate(ra)) || (rb.w - ra.w) || (b.backers.length - a.backers.length) || (b.total - a.total);
  });
}
function oppositeOf(p: Pick, game: Game): Pick[] {
  if (!p.mid) return [];
  return game.picks.filter((q: Pick) => q.key !== p.key && q.mid === p.mid && q.view.yesNo && q.view.yesNo !== p.view.yesNo);
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
  const top = p.backers.slice(0, 3);
  const rest = p.backers.slice(3);
  const colorOf = (x: string): string[] => (({ Core: ["#DBEAFE", "#1E3A8A"], "Top 50": ["#E0E7FF", "#3730A3"], Board: ["#F1F5F9", "#334155"], Weekly: ["#F1F5F9", "#334155"] } as Record<string, string[]>)[x] || ["#F1F5F9", "#334155"]);
  return (
    <div data-ucard={p.key} style={{ borderRadius: 18, border: "1.5px solid #BFDBFE", background: "#FFFFFF", boxShadow: "0 4px 14px rgba(11,31,51,0.08)", overflow: "hidden", marginBottom: 10, fontFamily: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }}>
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
  return (
    <div data-alt-bet={p.key} style={{ borderRadius: 14, border: "1.5px solid #BFDBFE", background: "#FFFFFF", padding: "10px 12px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 18, lineHeight: "22px", fontWeight: 850, overflowWrap: "anywhere", flex: 1, minWidth: 0, color: NAVY }}>{p.big}</div>
        <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 10, background: BLUE_BRIGHT, color: "#FFFFFF", fontSize: 18, fontWeight: 900, fontVariantNumeric: "tabular-nums" }}>{kMoney(p.total)}</span>
      </div>
      {p.sub ? <div style={{ fontSize: 13, fontWeight: 600, color: "#475569", marginTop: 2 }}>{p.sub}</div> : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 6 }}>
        <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 13, fontWeight: 850 }}>{p.backers.length + " capper" + (p.backers.length === 1 ? "" : "s")}</span>
        {p.tags.map((x: string) => <span key={x} style={{ display: "inline-block", padding: "1px 8px", borderRadius: 999, background: "#F1F5F9", color: "#334155", fontSize: 12, fontWeight: 800, border: "1px solid #94A3B8" }}>{x}</span>)}
      </div>
      <FreshPricePills p={p} now={props.now} />
      <div style={{ marginTop: 8 }}><KalshiBuyButton view={p.view} /></div>
      <OnKalshiBox view={p.view} />
      {p.backers.map((b: Backer) => <div key={b.name} style={{ fontSize: 13, lineHeight: "19px", fontWeight: 650, color: "#475569", marginTop: 2, overflowWrap: "anywhere" }}>{b.line}</div>)}
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
      {props.rec ? <span data-game-rec="1" style={{ display: "inline-block", padding: "2px 10px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 13, fontWeight: 850, border: "1.5px solid " + BLUE }}>{(props.rec.w + props.rec.l ? "Combined " + wlText(props.rec) + " · " + pctText(wlRate(props.rec)) : "No graded record") + (props.cappers ? " · " + props.cappers + " capper" + (props.cappers === 1 ? "" : "s") : "")}</span> : null}
    </div>
  );
}
function GameBlock(props: { g: Game; now: number; stake: string; showStart?: boolean; rankNo?: number; rec?: WL; cappers?: number; stakeLine?: string }) {
  const [open, setOpen] = useState(false);
  const picks = bestPickFirst(props.g.picks);
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

interface RankedCard { game: Game; rec: WL; cappers: number }
function gameRec(g: Game): { rec: WL; cappers: number } {
  const seen: Record<string, boolean> = {};
  let w = 0, l = 0;
  g.picks.forEach((p: Pick) => p.backers.forEach((b: Backer) => {
    if (seen[b.name]) return;
    seen[b.name] = true;
    if (b.rec) { w += b.rec.w; l += b.rec.l; }
  }));
  return { rec: { w, l }, cappers: Object.keys(seen).length };
}
function rankedLists(games: Game[]): { top: RankedCard[]; others: RankedCard[]; small: RankedCard[] } {
  const cards = games.map((game: Game) => ({ game, ...gameRec(game) }));
  const cmp = (a: RankedCard, b: RankedCard) => (wlRate(b.rec) - wlRate(a.rec)) || (b.rec.w - a.rec.w) || (b.cappers - a.cappers) || ((a.game.startTs || 1e12) - (b.game.startTs || 1e12));
  const big = cards.filter((c: RankedCard) => c.rec.w + c.rec.l >= ELITE_MIN_BETS).sort(cmp);
  const small = cards.filter((c: RankedCard) => c.rec.w + c.rec.l < ELITE_MIN_BETS).sort(cmp);
  return { top: big.slice(0, 15), others: big.slice(15), small };
}
interface CardPick { p: Pick; game: Game; n: number; stake: number }
function todayCard(games: Game[], now: number): { picks: CardPick[]; total: number } {
  const L = rankedLists(games);
  const order = L.top.concat(L.others, L.small);
  const eligible = (p: Pick, g: Game) => !g.live && g.startTs > now && p.view.price != null && !!p.view.yesNo && payoutOf(p) < 3;
  const warned = (p: Pick, g: Game) => { const c = sideCompare(p, g); return !!(c && c.verdict === "other"); };
  const rows: { p: Pick; game: Game; n: number }[] = [];
  order.forEach((c: RankedCard) => {
    const pick = bestPickFirst(c.game.picks).filter((p: Pick) => eligible(p, c.game))[0];
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
        <div style={{ fontSize: 13, fontWeight: 650, opacity: 0.9, marginTop: 4 }}>{"One pick per game, taken from the Ranked list below (best combined capper record first). Safer payouts (1.8x or less) first, nothing paying 3x or more, picks with the amber other-side warning last." + (freshN ? " " + freshN + " fresh." : "")}</div>
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
      <Text>{"Every open $500+ sports position from Kalshi traders who show their book, grouped by game and sorted by start time. Finished games are removed. Suggested $2–4 a ticket, about $40 a day. No parlays."}</Text>
      <div data-combined-summary="1" style={{ fontSize: 14, fontWeight: 750, color: "#475569", margin: "2px 2px 12px" }}>{pickN + " picks · " + props.games.length + " games · " + live.length + " live"}</div>
      {props.games.length === 0 ? <EmptyState title="No public Kalshi books right now" body={"None of the visible Sports-leaderboard traders has a $500+ open sports position starting within 24 hours. Most top traders hide their book."} /> : null}
      {live.length ? <div data-live-head="1" style={{ fontSize: 22, fontWeight: 900, margin: "10px 2px 2px", color: NAVY }}>{"Already started (" + live.length + ")"}</div> : null}
      {live.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart />)}
      {up.length ? <div data-all-today="1" style={{ fontSize: 22, fontWeight: 900, margin: "10px 2px 2px", color: NAVY }}>{"Upcoming (" + up.length + ")"}</div> : null}
      {up.map((g: Game) => <GameBlock key={g.id} g={g} now={props.now} stake="$2–4" showStart />)}
    </Section>
  );
}
function RankedTab(props: { games: Game[]; now: number }) {
  const L = rankedLists(props.games);
  const total = L.top.length + L.others.length + L.small.length;
  const render = (c: RankedCard, i: number) => <GameBlock key={c.game.id} g={c.game} now={props.now} stake="$2–4" rankNo={i + 1} rec={c.rec} cappers={c.cappers} />;
  return (
    <Section heading={"Ranked · " + total} caption={"Games ranked by the combined record of every capper on the card · starts or is live within 24 hours"}>
      <Text>{"Each game is one card. Its rank is the collective win ratio of every public capper betting on that game (all their wins divided by all their settled bets). Record counts, money does not. The $40 card on top takes one pick per game from this list. An amber warning names a capper on the other side with a better record."}</Text>
      <div data-ranked-summary="1" style={{ fontSize: 14, fontWeight: 750, color: "#475569", margin: "2px 2px 8px" }}>{total + " games · " + L.top.length + " in the top list"}</div>
      {total > 0 ? <TodayCard games={props.games} now={props.now} /> : null}
      {total === 0 ? <EmptyState title="No ranked games right now" body={"No visible Kalshi capper has a $500+ sports pick starting within 24 hours."} /> : null}
      {L.top.length ? <div data-elite-top="1" style={{ fontSize: 22, fontWeight: 900, margin: "4px 2px 4px", color: NAVY }}>{"Top " + L.top.length}</div> : null}
      {L.top.map((c: RankedCard, i: number) => render(c, i))}
      {L.others.length ? <div data-ranked-section="others" style={{ fontSize: 22, fontWeight: 900, margin: "18px 2px 4px", paddingTop: 10, borderTop: "3px solid " + BLUE, color: NAVY }}>{"All other games · " + L.others.length}</div> : null}
      {L.others.map((c: RankedCard, i: number) => render(c, L.top.length + i))}
      {L.small.length ? <div data-ranked-section="small" style={{ fontSize: 22, fontWeight: 900, margin: "18px 2px 4px", paddingTop: 10, borderTop: "3px solid " + BLUE, color: NAVY }}>{"Small sample (under " + ELITE_MIN_BETS + " bets) · " + L.small.length}</div> : null}
      {L.small.length ? <Text>{"The cappers on these games have fewer than 10 settled bets in total, so the record is not ranked with the main lists yet."}</Text> : null}
      {L.small.map((c: RankedCard, i: number) => render(c, L.top.length + L.others.length + i))}
    </Section>
  );
}
function CappersTab(props: { now: number }) {
  const caps = DATA.cappers || [];
  return (
    <Section heading={"Cappers · " + caps.length} caption={"Visible Sports-leaderboard traders. Hidden books are not listed."}>
      <Text>{"A capper has to show their bets on Kalshi to appear here. Core = in both the all-time and monthly top 50. Top 50 = on one of those boards. W-L is reconstructed from their public sports trade tape, not invented. Market makers are left out."}</Text>
      {caps.length === 0 ? <EmptyState title="No visible cappers right now" body={"Almost every name on Kalshi's Sports leaderboard hides their book."} /> : caps.map((c: Capper) => {
        const g = c.graded;
        return (
          <div key={c.nickname} data-capper={c.nickname} style={{ borderRadius: 16, border: "1.5px solid #BFDBFE", background: "#FFFFFF", padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
              <div style={{ fontSize: 17, fontWeight: 850, color: NAVY, overflowWrap: "anywhere" }}>{c.nickname}</div>
              <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, background: BLUE_SOFT, color: BLUE_INK, fontSize: 12, fontWeight: 850 }}>{c.tier}</span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#475569", marginTop: 4 }}>
              {g && g.n ? (g.w + "-" + g.l + " · " + pctText(g.w / Math.max(1, g.w + g.l)) + (g.roi != null ? " · " + (g.roi >= 0 ? "+" : "") + Math.round(g.roi) + "% ROI" : "") + (g.sample === "small" ? " · small sample" : "")) : "No graded sports record yet"}
              {c.pnl != null ? " · " + (c.pnl >= 0 ? "+" : "") + kMoney(c.pnl) + " all-time" : ""}
            </div>
            <div style={{ fontSize: 12, fontWeight: 650, color: "#64748B", marginTop: 2 }}>
              {(c.ranks && c.ranks.all_time ? "All-time #" + c.ranks.all_time : "") + (c.ranks && c.ranks.monthly ? " · Monthly #" + c.ranks.monthly : "") + (c.ranks && c.ranks.weekly ? " · Weekly #" + c.ranks.weekly : "") + (c.pickCount ? " · " + c.pickCount + " open pick" + (c.pickCount === 1 ? "" : "s") : " · no open $500+ pick in the window")}
            </div>
            {c.profileUrl ? <a href={c.profileUrl} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 800, color: BLUE, textDecoration: "none" }}>Kalshi profile ↗</a> : null}
          </div>
        );
      })}
    </Section>
  );
}

export default function App() {
  const [tab, setTab] = useState<"coming" | "ranked" | "cappers">("coming");
  const now = Math.round(Date.now() / 1000);
  const games = useMemo(() => openGames(now), [now]);
  const comingN = games.reduce((n: number, g: Game) => n + g.picks.length, 0);
  const cov = (DATA.source && DATA.source.coverage) || {};
  const tabs = [
    { value: "coming" as const, label: "Coming Up", count: comingN },
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
        {tab === "ranked" ? <RankedTab games={games} now={now} /> : null}
        {tab === "cappers" ? <CappersTab now={now} /> : null}
        <details style={{ marginTop: 18, padding: "10px 12px", borderRadius: 14, background: "#FFFFFF", border: "1px solid #BFDBFE" }}>
          <summary style={{ cursor: "pointer", fontWeight: 800, color: BLUE }}>How this is sourced</summary>
          <p style={{ fontSize: 13, lineHeight: "19px", color: "#475569" }}>{(DATA.source && DATA.source.note) || "Kalshi Sports leaderboard, public profiles, and the public trade tape."}</p>
          <p style={{ fontSize: 13, lineHeight: "19px", color: "#475569" }}>{"Visible books " + (cov.visible || 0) + " · hidden " + (cov.hidden || 0) + " · monthly∩all-time top 50 = " + (cov.intersection50 || 0) + ". Kalshi period used: " + ((DATA.source && DATA.source.periodUsed) || "monthly") + "."}</p>
        </details>
      </div>
    </div>
  );
}
