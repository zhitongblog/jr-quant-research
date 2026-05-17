// API client for the jr-dashboard FastAPI backend.

const STORAGE_KEY = "jr.apiBase";
const DEFAULT_BASE =
  (import.meta.env.VITE_JR_API as string | undefined) ?? "http://127.0.0.1:8765";

export function getApiBase(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}
export function setApiBase(url: string) {
  try {
    localStorage.setItem(STORAGE_KEY, url.replace(/\/$/, ""));
  } catch { /* ignore */ }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${getApiBase()}${path}`, init);
  if (!r.ok) {
    const detail = await r.text().catch(() => "");
    throw new Error(`${r.status} ${r.statusText} ${detail}`);
  }
  return (await r.json()) as T;
}

// ---------- Types ----------

export interface Health {
  ok: boolean;
  proj_root: string;
  qlib_data_exists: boolean;
  paper_trades_exists: boolean;
  n_portfolios: number;
  n_predictions: number;
  data_last_date: string | null;
  server_time: string;
}

export interface NewsItem {
  source: string;
  date: string;
  title: string;
  summary: string;
  url: string;
}

export interface NewsRecent {
  refreshed_at: string | null;
  days_back?: number;
  by_source?: Record<string, number>;
  n_items: number;
  items: NewsItem[];
  message?: string;
}

export interface Holding {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_code: string;
  sw1_name: string;
}

export interface LlmPick {
  sw1_code: string;
  sw1_name: string;
  rationale: string;
}

export interface Portfolio {
  date: string;
  path_a: { name: string; holdings: Holding[] };
  path_d: {
    name: string;
    holdings: Holding[];
    llm_picks: LlmPick[];
    llm_macro: string;
  };
  ensemble: {
    name: string;
    intersection_size: number;
    holdings: Holding[];
  };
}

export interface LlmLatest {
  date: string;
  backend: string;
  model: string;
  elapsed_s: number;
  picks: LlmPick[];
  macro_view: string;
  n_holdings: number;
}

export interface BacktestRow {
  version: string;
  name: string;
  cum_net: number | null;
  sharpe: number | null;
  max_dd: number | null;
}

export interface PerformanceRow {
  prediction_date: string;
  eval_date?: string;
  csi300_cum_ret?: number;
  path_a_cum_ret?: number;
  path_a_excess?: number;
  path_d_cum_ret?: number;
  path_d_excess?: number;
  ensemble_cum_ret?: number;
  ensemble_excess?: number;
}

export interface FactorSnapshot {
  as_of: string;
  close: number;
  volume: number;
  amount: number;
  ret_1d: number | null;
  limit_up_reversal_20d: number | null;
  price_volume_divergence: number | null;
  amihud_illiquidity_20d: number | null;
}

export interface IndustryRank {
  rank: number | null;
  total: number;
  industry_mean: number;
}

export interface Peer {
  qlib_symbol: string;
  symbol: string;
  name: string;
  close: number;
  ret_1d: number | null;
  limit_up_reversal_20d: number | null;
  price_volume_divergence: number | null;
  amihud_illiquidity_20d: number | null;
  combo: number;
  roe_weighted: number | null;
  earnings_yoy: number | null;
  gross_margin: number | null;
  debt_ratio: number | null;
}

export interface Fundamentals {
  as_of: string;
  prev_as_of?: string;
  roe_weighted?: number;
  roe?: number;
  earnings_yoy?: number;
  gross_margin?: number;
  op_margin?: number;
  debt_ratio?: number;
  current_ratio?: number;
  prev_roe_weighted?: number;
  prev_roe?: number;
  prev_earnings_yoy?: number;
  prev_gross_margin?: number;
  prev_op_margin?: number;
  prev_debt_ratio?: number;
  prev_current_ratio?: number;
}

export interface PriceSummary {
  as_of: string;
  close: number;
  week_52_high: number;
  week_52_low: number;
  week_52_position_pct: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  ma_status?: "bullish" | "bearish" | "mixed";
  volume_ratio_5d?: number;
}

export interface StockDetail {
  info: { symbol: string; name: string; sw1_code: string; sw1_name: string };
  factors_latest: FactorSnapshot | null;
  industry_relative: Record<string, number>;
  industry_rank: Record<string, IndustryRank>;
  industry_size: number;
  peers: Peer[];
  fundamentals: Fundamentals | null;
  price_summary: PriceSummary | null;
  in_portfolio: {
    path_a: boolean;
    path_d: boolean;
    ensemble: boolean;
  };
}

export interface PriceRow {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  amount: number;
  ret1: number | null;
  limit_up: boolean;
}

export interface StockPrices {
  info: { symbol: string; name: string; sw1_code: string; sw1_name: string };
  rows: PriceRow[];
}

export interface JobStatus {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  command: string;
  tail: string[];
  n_lines: number;
  started_at?: number;
  ended_at?: number;
  return_code?: number;
  error?: string;
}

// ---------- Endpoints ----------

export const api = {
  health: () => fetchJSON<Health>("/api/health"),
  portfolioLatest: () => fetchJSON<Portfolio>("/api/portfolio/latest"),
  portfolioHistory: () => fetchJSON<{ dates: string[] }>("/api/portfolio/history"),
  portfolioByDate: (date: string) => fetchJSON<Portfolio>(`/api/portfolio/${date}`),
  llmLatest: () => fetchJSON<LlmLatest>("/api/llm/latest"),
  backtestComparison: () => fetchJSON<{ rows: BacktestRow[] }>("/api/backtest/comparison"),
  performanceTimeseries: () =>
    fetchJSON<{ rows: PerformanceRow[]; message?: string }>("/api/performance/timeseries"),
  runMonthlyUpdate: () =>
    fetchJSON<{ task_id: string; status: string }>("/api/run/monthly_update", { method: "POST" }),
  runStatus: (taskId: string) => fetchJSON<JobStatus>(`/api/run/status/${taskId}`),
  stockDetail: (symbol: string) => fetchJSON<StockDetail>(`/api/stock/${symbol}`),
  stockPrices: (symbol: string, days = 120) =>
    fetchJSON<StockPrices>(`/api/stock/${symbol}/prices?days=${days}`),
  pricesLatest: (symbols: string[]) =>
    fetchJSON<{ rows: PriceLatestRow[] }>(
      `/api/prices/latest?symbols=${encodeURIComponent(symbols.join(","))}`
    ),
  etfComparison: (days = 252) =>
    fetchJSON<EtfComparison>(`/api/etf/comparison?days=${days}`),
  tradesList: () => fetchJSON<{ rows: Trade[]; count: number }>(`/api/trades`),
  tradesAdd: (t: TradeIn) =>
    fetchJSON<Trade>(`/api/trades`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(t),
    }),
  tradesUpdate: (id: string, t: TradeIn) =>
    fetchJSON<Trade>(`/api/trades/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(t),
    }),
  tradesDelete: (id: string) =>
    fetchJSON<{ deleted: string }>(`/api/trades/${id}`, { method: "DELETE" }),
  tradesPositions: () => fetchJSON<PositionsResponse>(`/api/trades/positions`),
  tradesImport: async (file: File, commit: boolean): Promise<ImportPreview> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${getApiBase()}/api/trades/import?commit=${commit}`, {
      method: "POST",
      body: form,
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return (await r.json()) as ImportPreview;
  },
  stocksSearch: (q: string) =>
    fetchJSON<{ rows: StockSearchRow[] }>(`/api/stocks/search?q=${encodeURIComponent(q)}`),
  newsRecent: (limit = 30) => fetchJSON<NewsRecent>(`/api/news/recent?limit=${limit}`),
  newsRefresh: () =>
    fetchJSON<{ task_id: string; status: string }>(`/api/news/refresh`, { method: "POST" }),
  newsContextGet: () => fetchJSON<{ text: string }>(`/api/news/context`),
  newsContextSet: (text: string) =>
    fetchJSON<{ ok: boolean; n_chars: number }>(`/api/news/context`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  secretsStatus: () => fetchJSON<SecretsStatus>(`/api/secrets/status`),
  setDeepseek: (api_key: string, model = "deepseek-v4-pro", api_base = "https://api.deepseek.com") =>
    fetchJSON<{ ok: boolean }>(`/api/secrets/deepseek`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, model, api_base }),
    }),
  clearDeepseek: () =>
    fetchJSON<{ ok: boolean }>(`/api/secrets/deepseek`, { method: "DELETE" }),
};

export interface SecretsStatus {
  deepseek_set: boolean;
  deepseek_key_preview: string;
  deepseek_model: string;
  deepseek_api_base: string;
}

export interface PriceLatestRow {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_name: string;
  close: number | null;
}

export interface Trade {
  id: string;
  trade_date: string;
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_code: string;
  sw1_name: string;
  side: "buy" | "sell";
  shares: number;
  price: number;
  fee: number;
  note: string;
  amount: number;
}

export interface TradeIn {
  trade_date: string;
  qlib_symbol: string;
  side: "buy" | "sell";
  shares: number;
  price: number;
  fee?: number;
  note?: string;
}

export interface Position {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_name: string;
  shares: number;
  cost_basis: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  pnl_pct: number | null;
}

export interface PositionsResponse {
  positions: Position[];
  summary: {
    n_positions: number;
    total_cost_basis: number;
    total_market_value: number;
    unrealized_pnl: number;
    realized_pnl: number;
    total_pnl: number;
    pnl_pct: number | null;
  };
}

export interface StockSearchRow {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_name: string;
}

export interface ImportPreview {
  ok: boolean;
  encoding?: string;
  filename?: string;
  column_mapping?: Record<string, string | null>;
  n_parsed?: number;
  n_errors?: number;
  errors?: { row: number; reason: string }[];
  preview?: Trade[];
  committed?: boolean;
  error?: string;
  headers?: string[];
}

export interface EtfComparison {
  rows?: never;
  etf_drag_assumption_annual: number;
  csi300_index?: { date: string; cum_ret: number }[];
}
