// Server-side reads from the local Signal Desk API. Never throws: a down API reads as null and pages say so.
const API = process.env.WHALEPROOF_API ?? "http://127.0.0.1:8100";

export async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${API}${path}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

export type Value = { verdict: "cheap" | "fair" | "rich" | "unknown"; reason: string; iv: number | null;
  rv: number | null; iv_rv: number | null; iv_rank: number | null } | null;
export type Signal = {
  id: string; ticker: string; direction: number; tier: "whale" | "far_otm"; label: string; why: string[];
  premium: number; kind: string; strike: number; expiry: string; dte: number; otm_pct: number; spot_at_alert: number;
  contract: string; created_at: string; sweep: boolean; iv: number | null; value: Value; repeat: number;
  sector: string | null; session_date: string; entry: string; exit_by: string;
  next_earnings: { date: string; time: string } | null; cluster: { sector: string; n: number } | null;
  entry_price?: number | null; last_price?: number | null; since_entry?: number | null; since_entry_net?: number | null; hold_day?: number; price_source?: string;
  today_move?: number | null; today_day?: string | null; price_now?: number | null; today_since?: "entry_open" | "prev_close" | null;
  iv_rank?: number | null; gex?: Gex | null; gex_date?: string | null; dp_levels?: [number, number][];
  accumulation?: { buys: number; days: number; premium: number; sessions: number };
  earnings_warning?: EarnWarn | null; size?: number | null; watch_only?: boolean; spot_at?: string | null; gex_stale?: boolean; dp_stale?: boolean;
  quote?: { bid: number | null; ask: number | null; last: number | null; volume: number | null; open_interest: number | null;
    iv: number | null; at: string | null } | null;
  oi?: { trail: { date: string; oi: number }[]; next_morning: { date: string; change: number; ratio: number | null } | null;
    confirmed: boolean | null; latest: { date: string; oi: number } | null;
    record?: { unconfirmed: { trades: number; mean_vs_spy: number | null }; confirmed: { trades: number; mean_vs_spy: number | null };
      difference_range: [number, number] | null } | null };
};
export type EarnWarn = { date: string; time: string; last_session_before: string; text: string };
export type Gex = { call_wall: number | null; put_wall: number | null; gamma_flip: number | null;
  gamma_magnet: number | null; date?: string };
export type Spot = { last: number | null; open: number | null; prev_close: number | null; market_time?: string };
export type Funnel = { raw: number; directional: number; clean: number; signals: number };
export type Stats = { n: number; days: number; win_rate?: number; mean?: number; median?: number; day_mean?: number;
  profit_factor?: number | null; ci_low?: number | null; ci_high?: number | null; avg_win?: number | null; avg_loss?: number | null };
export type Rejected = { ticker: string; direction: number; kind: string; premium: number; strike: number;
  expiry: string; dte: number; otm_pct: number; stage: string; reason: string; created_at: string };
export type EvWindow = { label: string; funnel: Funnel & { days: number; per_day: Funnel }; signals: Stats;
  all: Stats; clean: Stats; unpriced?: number | null; open?: number | null } | null;
export type Status = {
  clock: { state: "pre" | "open" | "after" | "closed"; label: string; now: string; next_open: string; close?: string };
  data_day: string; refreshed_at: string | null;
  usage: { count?: number | null; count_at?: string | null; limit?: number; reserve?: number; burn_per_min?: number | null; pace?: number | null; stopped?: boolean; mode?: string; live_now?: boolean };
  quota_exhausted: boolean; blocked: boolean; auth_failed: boolean; live_enabled: boolean;
  failing: Record<string, string>; sources_ok: number; sources_total: number;
};
export type Fresh = { at: string | null; age_s: number | null; stale: boolean };
export type TidePoint = { t: string; call: number; put: number; net: number };

/** Exploratory holding-period study (journal/research/holding-period.json). */
export type HStat = { trades: number; avg_per_trade?: number; avg_per_session_held?: number; win_rate?: number;
  range95_day_mean?: [number | null, number | null]; range_includes_zero?: boolean | null };
export type Holding = { horizons: number[]; periods: Record<string, { name: string; signals_excluded_short_future: number;
  by_horizon: Record<string, { signals: HStat; every_alert: HStat; share_with_earnings_inside: number | null }> }> };

// Earnings (W2, exploratory): UW implied move vs the ticker's own past report moves.
export type EarnPast = { day: string; time: string; implied: number | null; actual: number; beat: boolean | null };
export type EarnLabel = "cheap" | "fair" | "rich";
export type EarnRow = { ticker: string; date: string; time: string; implied: number | null; past: number | null;
  ratio: number | null; label: EarnLabel | null; note: string | null; sector: string | null; marketcap: number | null;
  history_reports: number; history: EarnPast[]; from_history?: boolean; reported?: boolean };
export type EarnStat = { reports: number; beat: number; median_move_vs_implied: number; mean_edge: number };
export type EarnBacktest = { run: string; scored: number; verdict: string; all: EarnStat;
  by_label: Record<EarnLabel, EarnStat>; by_label_year: Record<EarnLabel, Record<string, EarnStat>>;
  cheap_minus_rich_beat: { all: number; range95: [number, number]; by_year: Record<string, number> };
  sensitivity: { dropped: number; by_label: Record<EarnLabel, EarnStat> } };
export type Earnings = { at: string | null; upcoming: EarnRow[]; sessions: string[]; backtest: EarnBacktest | null;
  thresholds: { cheap_below: number; rich_above: number; min_past: number; max_past: number } };
export type EarnCard = { ticker: string; next: EarnRow | null; history: EarnPast[];
  scored: { day: string; label: EarnLabel; beat: boolean; ratio: number }[] };
