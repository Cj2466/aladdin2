import axios, { isAxiosError } from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
// Live quotes carry no auth cookie, so this can point straight at the
// backend even when API_BASE_URL is proxied same-origin in production
// (see functions/api/[[path]].js) — proxying a WebSocket through a Pages
// Function is unreliable and unnecessary here.
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? API_BASE_URL;

export const apiClient = axios.create({ baseURL: API_BASE_URL, withCredentials: true });

// The auth session lives in an httpOnly cookie the browser manages — the
// frontend never touches a token. The only signal a session has expired is
// a 401 on some later request; AuthContext registers a handler here so it
// can clear its user state without every call site needing to know about it.
type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isAxiosError(error) && error.response?.status === 401) {
      unauthorizedHandler?.();
    }
    return Promise.reject(error);
  },
);

export interface HoldingInput {
  ticker: string;
  weight: number;
}

export interface PortfolioAnalyzeRequest {
  holdings: HoldingInput[];
  benchmark: string;
  lookback_years: number;
}

export interface PortfolioAnalyzeResponse {
  as_of: string;
  volatility_annualized: number;
  var_historical_95: number;
  var_parametric_95: number;
  cvar_95: number;
  beta: number;
  hhi: number;
  avg_pairwise_correlation: number;
  correlation_matrix: Record<string, Record<string, number>>;
  warnings: string[];
}

export interface ApiErrorBody {
  detail?: string;
}

export async function analyzePortfolio(
  request: PortfolioAnalyzeRequest,
): Promise<PortfolioAnalyzeResponse> {
  const { data } = await apiClient.post<PortfolioAnalyzeResponse>(
    "/api/portfolios/analyze",
    request,
  );
  return data;
}

export function liveQuotesWsUrl(): string {
  const wsProtocol = WS_BASE_URL.startsWith("https") ? "wss" : "ws";
  const host = WS_BASE_URL.replace(/^https?:\/\//, "");
  return `${wsProtocol}://${host}/ws/live-quotes`;
}

// --- Auth ---------------------------------------------------------------

export interface UserOut {
  id: number;
  email: string;
}

export interface RegisterResponse {
  email: string;
  message: string;
}

export async function registerUser(
  email: string,
  password: string,
  acceptedTerms: boolean,
): Promise<RegisterResponse> {
  const { data } = await apiClient.post<RegisterResponse>("/api/auth/register", {
    email,
    password,
    accepted_terms: acceptedTerms,
  });
  return data;
}

export async function forgotPassword(email: string): Promise<void> {
  await apiClient.post("/api/auth/forgot-password", { email });
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await apiClient.post("/api/auth/reset-password", { token, new_password: newPassword });
}

export async function verifyEmailToken(token: string): Promise<UserOut> {
  const { data } = await apiClient.post<UserOut>("/api/auth/verify-email", { token });
  return data;
}

export async function resendVerification(email: string): Promise<void> {
  await apiClient.post("/api/auth/resend-verification", { email });
}

export async function loginUser(email: string, password: string): Promise<UserOut> {
  const { data } = await apiClient.post<UserOut>("/api/auth/login", { email, password });
  return data;
}

export async function logoutUser(): Promise<void> {
  await apiClient.post("/api/auth/logout");
}

export async function fetchCurrentUser(): Promise<UserOut | null> {
  try {
    const { data } = await apiClient.get<UserOut>("/api/auth/me");
    return data;
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 401) {
      return null;
    }
    throw error;
  }
}

// --- Saved portfolios -----------------------------------------------------

export interface HoldingOut {
  id: number;
  ticker: string;
  weight: number | null;
}

export interface PortfolioSummary {
  id: number;
  name: string;
  base_currency: string;
  updated_at: string;
  holding_count: number;
}

export interface PortfolioOut {
  id: number;
  name: string;
  base_currency: string;
  created_at: string;
  updated_at: string;
  holdings: HoldingOut[];
}

export interface PortfolioWriteRequest {
  name: string;
  base_currency?: string;
  holdings: HoldingInput[];
}

export interface SavedPortfolioAnalyzeResponse extends PortfolioAnalyzeResponse {
  portfolio_id: number;
  cached: boolean;
}

export async function listPortfolios(): Promise<PortfolioSummary[]> {
  const { data } = await apiClient.get<PortfolioSummary[]>("/api/portfolios");
  return data;
}

export async function createPortfolio(request: PortfolioWriteRequest): Promise<PortfolioOut> {
  const { data } = await apiClient.post<PortfolioOut>("/api/portfolios", request);
  return data;
}

export async function getPortfolio(id: number): Promise<PortfolioOut> {
  const { data } = await apiClient.get<PortfolioOut>(`/api/portfolios/${id}`);
  return data;
}

export async function updatePortfolio(
  id: number,
  request: PortfolioWriteRequest,
): Promise<PortfolioOut> {
  const { data } = await apiClient.put<PortfolioOut>(`/api/portfolios/${id}`, request);
  return data;
}

export async function deletePortfolio(id: number): Promise<void> {
  await apiClient.delete(`/api/portfolios/${id}`);
}

export async function analyzeSavedPortfolio(
  id: number,
  benchmark: string,
  lookbackYears: number,
): Promise<SavedPortfolioAnalyzeResponse> {
  const { data } = await apiClient.get<SavedPortfolioAnalyzeResponse>(
    `/api/portfolios/${id}/analyze`,
    { params: { benchmark, lookback_years: lookbackYears } },
  );
  return data;
}

// --- Stress testing / sector exposure -------------------------------------

export interface HoldingStressOut {
  ticker: string;
  weight: number;
  return_pct: number;
  basis: "actual" | "estimated";
}

export interface ScenarioMacroContextOut {
  series_id: string;
  label: string;
  unit: "percent" | "usd_trillions";
  decimals: number;
  start_value: number | null;
  start_observation_date: string | null;
  current_value: number | null;
  current_observation_date: string | null;
}

export interface ScenarioOut {
  scenario_id: string;
  label: string;
  description: string;
  start: string;
  end: string;
  portfolio_return: number;
  benchmark_return: number;
  has_estimated: boolean;
  holdings: HoldingStressOut[];
  macro_context: ScenarioMacroContextOut[];
}

export interface ExposureSliceOut {
  label: string;
  weight: number;
}

export interface StressTestResponse {
  scenarios: ScenarioOut[];
  sector_exposure: ExposureSliceOut[];
  asset_class_exposure: ExposureSliceOut[];
  warnings: string[];
}

export interface StressTestRequest {
  holdings: HoldingInput[];
  benchmark: string;
}

export async function stressTestPortfolio(
  request: StressTestRequest,
): Promise<StressTestResponse> {
  const { data } = await apiClient.post<StressTestResponse>(
    "/api/portfolios/stress-test",
    request,
  );
  return data;
}

export async function stressTestSavedPortfolio(
  id: number,
  benchmark: string,
): Promise<StressTestResponse> {
  const { data } = await apiClient.get<StressTestResponse>(`/api/portfolios/${id}/stress-test`, {
    params: { benchmark },
  });
  return data;
}

// --- Portfolio optimizer ---------------------------------------------------

export interface OptimizedHoldingOut {
  ticker: string;
  weight: number;
}

export interface PortfolioOptimizeResponse {
  as_of: string;
  lookback_years: number;
  risk_free_rate: number;
  max_weight_cap: number;
  optimized_weights: OptimizedHoldingOut[];
  optimized_expected_return: number;
  optimized_volatility: number;
  optimized_sharpe: number;
  current_expected_return: number;
  current_volatility: number;
  current_sharpe: number;
  warnings: string[];
}

export interface SavedPortfolioOptimizeResponse extends PortfolioOptimizeResponse {
  portfolio_id: number;
}

export interface PortfolioOptimizeRequest {
  holdings: HoldingInput[];
  lookback_years: number;
}

export async function optimizePortfolio(
  request: PortfolioOptimizeRequest,
): Promise<PortfolioOptimizeResponse> {
  const { data } = await apiClient.post<PortfolioOptimizeResponse>(
    "/api/portfolios/optimize",
    request,
  );
  return data;
}

export async function optimizeSavedPortfolio(
  id: number,
  lookbackYears: number,
): Promise<SavedPortfolioOptimizeResponse> {
  const { data } = await apiClient.get<SavedPortfolioOptimizeResponse>(
    `/api/portfolios/${id}/optimize`,
    { params: { lookback_years: lookbackYears } },
  );
  return data;
}

// --- Factor risk decomposition ----------------------------------------------

export interface FactorExposureOut {
  factor: string;
  label: string;
  exposure: number;
  contribution_pct: number;
}

export interface HoldingFactorFitOut {
  ticker: string;
  betas: Record<string, number>;
  r_squared: number;
  idiosyncratic_volatility_annualized: number;
}

export interface PortfolioFactorRiskResponse {
  as_of: string;
  lookback_years: number;
  factor_detail: FactorExposureOut[];
  risk_contribution: ExposureSliceOut[];
  idiosyncratic_risk_pct: number;
  factor_variance_annualized: number;
  idiosyncratic_variance_annualized: number;
  total_variance_annualized: number;
  holdings: HoldingFactorFitOut[];
  warnings: string[];
}

export interface SavedPortfolioFactorRiskResponse extends PortfolioFactorRiskResponse {
  portfolio_id: number;
}

export interface PortfolioFactorRiskRequest {
  holdings: HoldingInput[];
  lookback_years: number;
}

export async function computeFactorRisk(
  request: PortfolioFactorRiskRequest,
): Promise<PortfolioFactorRiskResponse> {
  const { data } = await apiClient.post<PortfolioFactorRiskResponse>(
    "/api/portfolios/factor-risk",
    request,
  );
  return data;
}

export async function computeFactorRiskForSavedPortfolio(
  id: number,
  lookbackYears: number,
): Promise<SavedPortfolioFactorRiskResponse> {
  const { data } = await apiClient.get<SavedPortfolioFactorRiskResponse>(
    `/api/portfolios/${id}/factor-risk`,
    { params: { lookback_years: lookbackYears } },
  );
  return data;
}

// --- Report export ----------------------------------------------------------

export async function exportPortfolioReport(
  id: number,
  format: "csv" | "pdf",
  benchmark: string,
  lookbackYears: number,
): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/api/portfolios/${id}/export`, {
    params: { format, benchmark, lookback_years: lookbackYears },
    responseType: "blob",
  });
  return data;
}

// --- Alerts -----------------------------------------------------------------

export type AlertRuleType = "price_move" | "risk_metric" | "macro_threshold";
export type AlertDirection = "up" | "down";

export const RISK_METRIC_OPTIONS = [
  "volatility_annualized",
  "var_historical_95",
  "var_parametric_95",
  "cvar_95",
  "beta",
  "hhi",
  "avg_pairwise_correlation",
] as const;

export interface AlertRuleOut {
  id: number;
  portfolio_id: number | null;
  rule_type: AlertRuleType;
  ticker: string | null;
  metric: string | null;
  series_id: string | null;
  threshold_pct: number;
  direction: AlertDirection;
  is_active: boolean;
  last_checked_at: string | null;
  last_fired_at: string | null;
  created_at: string;
}

export interface AlertEventOut {
  id: number;
  alert_rule_id: number;
  message: string;
  triggered_value: number;
  created_at: string;
  is_read: boolean;
  email_sent: boolean;
}

export interface AlertRuleCreateRequest {
  portfolio_id?: number | null;
  rule_type: AlertRuleType;
  ticker?: string | null;
  metric?: string | null;
  series_id?: string | null;
  threshold_pct: number;
  direction: AlertDirection;
}

export async function listAlertRules(): Promise<AlertRuleOut[]> {
  const { data } = await apiClient.get<AlertRuleOut[]>("/api/alerts/rules");
  return data;
}

export async function createAlertRule(request: AlertRuleCreateRequest): Promise<AlertRuleOut> {
  const { data } = await apiClient.post<AlertRuleOut>("/api/alerts/rules", request);
  return data;
}

export async function deleteAlertRule(id: number): Promise<void> {
  await apiClient.delete(`/api/alerts/rules/${id}`);
}

export async function listAlertEvents(): Promise<AlertEventOut[]> {
  const { data } = await apiClient.get<AlertEventOut[]>("/api/alerts");
  return data;
}

export async function markAlertEventRead(id: number): Promise<AlertEventOut> {
  const { data } = await apiClient.patch<AlertEventOut>(`/api/alerts/${id}/read`);
  return data;
}

// --- Macro environment --------------------------------------------------

export type MacroCadence = "daily" | "monthly" | "quarterly" | "irregular";
export type MacroCategory = "inflation" | "rates" | "debt" | "growth" | "nowcasts";

export interface MacroSeriesOut {
  series_id: string;
  label: string;
  category: MacroCategory;
  cadence: MacroCadence;
  unit: "percent" | "usd_trillions";
  decimals: number;
  value: number | null;
  observation_date: string | null;
  reference_period_label: string | null;
  fetched_at: string | null;
  next_release_hint: string;
  status: "ok" | "unavailable";
}

export interface YieldCurvePointOut {
  maturity_label: string;
  today: number | null;
  one_year_ago: number | null;
}

export interface MacroDashboardResponse {
  series: MacroSeriesOut[];
  yield_curve: YieldCurvePointOut[];
  generated_at: string;
}

export async function getMacroDashboard(): Promise<MacroDashboardResponse> {
  const { data } = await apiClient.get<MacroDashboardResponse>("/api/macro/dashboard");
  return data;
}

export interface MacroSeriesCatalogEntry {
  series_id: string;
  label: string;
  category: MacroCategory;
  unit: "percent" | "usd_trillions";
}

export async function listMacroSeries(): Promise<MacroSeriesCatalogEntry[]> {
  const { data } = await apiClient.get<MacroSeriesCatalogEntry[]>("/api/macro/series");
  return data;
}

export type ReturnStatus = "ok" | "too_recent" | "benchmark_unavailable";

export interface EpisodeOutcomeOut {
  episode_start: string;
  episode_end: string;
  trading_days_in_episode: number;
  return_6m: number | null;
  return_6m_status: ReturnStatus;
  return_12m: number | null;
  return_12m_status: ReturnStatus;
  return_18m: number | null;
  return_18m_status: ReturnStatus;
}

export interface HistoricalAnalogResponse {
  series_id: string;
  series_label: string;
  threshold: number;
  direction: "up" | "down";
  benchmark: string;
  history_start: string;
  history_end: string;
  episode_count: number;
  episodes: EpisodeOutcomeOut[];
  caveat: string;
}

export async function getHistoricalAnalog(
  seriesId: string,
  benchmark: string,
): Promise<HistoricalAnalogResponse> {
  const { data } = await apiClient.get<HistoricalAnalogResponse>("/api/macro/historical-analog", {
    params: { series_id: seriesId, benchmark },
  });
  return data;
}

export interface MacroHistoryPointOut {
  date: string;
  value: number;
}

export type TrendStrength = "weak" | "moderate" | "strong";

export interface SeriesProjectionOut {
  series_id: string;
  label: string;
  unit: "percent" | "usd_trillions";
  decimals: number;
  status: "ok" | "insufficient_history";
  as_of_date: string | null;
  last_value: number | null;
  recent_history: MacroHistoryPointOut[];
  horizon_trading_days: number;
  horizon_label: string;
  point_estimate: number | null;
  band_low: number | null;
  band_high: number | null;
  band_confidence_pct: number;
  r_squared: number | null;
  trend_strength: TrendStrength | null;
  point_estimate_outside_historical_range: boolean | null;
}

export interface SeriesProjectionsResponse {
  projections: SeriesProjectionOut[];
  generated_at: string;
  methodology_note: string;
}

export async function getSeriesProjections(): Promise<SeriesProjectionsResponse> {
  const { data } = await apiClient.get<SeriesProjectionsResponse>("/api/macro/projections");
  return data;
}

// --- Individual stock analysis -------------------------------------------

export interface RecommendationTrendOut {
  period: string;
  strong_buy: number;
  buy: number;
  hold: number;
  sell: number;
  strong_sell: number;
}

export interface StockFundamentalsOut {
  ticker: string;
  company_name: string | null;
  exchange: string | null;
  country: string | null;
  currency: string | null;
  ipo_date: string | null;
  market_capitalization: number | null;
  share_outstanding: number | null;
  finnhub_industry: string | null;
  weburl: string | null;
  logo: string | null;
  week52_high: number | null;
  week52_low: number | null;
  beta: number | null;
  pe_ttm: number | null;
  eps_ttm: number | null;
  roe_ttm: number | null;
  roa_ttm: number | null;
  gross_margin_ttm: number | null;
  net_margin_ttm: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
  debt_to_equity: number | null;
  dividend_yield_ttm: number | null;
  avg_10day_volume: number | null;
  recommendation_trend: RecommendationTrendOut[];
  peers: string[];
  fetched_at: string;
}

export interface StockAnalysisResponse {
  fundamentals: StockFundamentalsOut;
  macro_context: MacroSeriesOut[];
  generated_at: string;
}

export async function getStockAnalysis(ticker: string): Promise<StockAnalysisResponse> {
  const { data } = await apiClient.get<StockAnalysisResponse>(
    `/api/stocks/${encodeURIComponent(ticker)}/analysis`,
  );
  return data;
}

// --- Research lab: pairs mean-reversion backtest (OU / AR(1)) -----------

export interface PairsBacktestRequest {
  ticker_a: string;
  ticker_b: string;
  fit_window_days?: number;
  entry_z?: number;
  exit_z?: number;
  cost_bps?: number;
  lookback_years?: number;
}

export type PairsBacktestStatus = "ok" | "not_mean_reverting" | "insufficient_history" | "not_trending";
export type FitQuality = "weak" | "moderate" | "strong";

export interface EquityCurvePointOut {
  date: string;
  equity: number;
  position: number;
  z_score: number | null;
}

export interface TradeOut {
  entry_date: string;
  exit_date: string | null;
  direction: "long_spread" | "short_spread" | "long" | "short";
  holding_days: number;
  trade_return: number;
  still_open: boolean;
}

export interface SearchContextOut {
  configurations_tested: number;
  note: string;
}

export interface DeflatedSharpeOut {
  sharpe_net_annualized: number;
  sharpe_net_daily: number;
  n_observations: number;
  skewness: number;
  kurtosis: number;
  psr_vs_zero: number | null;
  n_trials: number;
  sigma_sr_annualized: number | null;
  expected_max_sharpe_noise_annualized: number | null;
  dsr: number | null;
  dsr_floor_met: boolean;
  interpretation: string;
}

export interface PairsBacktestResponse {
  status: PairsBacktestStatus;
  strategy_name: string;
  as_of: string;
  ticker_a: string;
  ticker_b: string;
  fit_window_days: number;
  entry_z: number;
  exit_z: number;
  cost_bps: number;
  lookback_years: number;
  n_trading_days: number;
  n_out_of_sample_days: number;
  total_return_net: number | null;
  annualized_return_net: number | null;
  annualized_volatility_net: number | null;
  sharpe_net: number | null;
  sharpe_gross: number | null;
  max_drawdown_net: number | null;
  num_trades: number;
  win_rate: number | null;
  exposure_pct: number | null;
  total_cost_drag: number | null;
  pct_days_mean_reverting: number;
  fit_quality_distribution: Record<FitQuality, number>;
  equity_curve: EquityCurvePointOut[];
  trade_log: TradeOut[];
  search_context: SearchContextOut;
  methodology_note: string;
  warnings: string[];
  cached: boolean;
  deflated_sharpe: DeflatedSharpeOut | null;
}

export async function runPairsBacktest(request: PairsBacktestRequest): Promise<PairsBacktestResponse> {
  const { data } = await apiClient.post<PairsBacktestResponse>("/api/research-lab/pairs-backtest", request);
  return data;
}

// --- Research lab: momentum / trend-following backtest ---------------------

export interface MomentumBacktestRequest {
  ticker: string;
  fit_window_days?: number;
  entry_z?: number;
  exit_z?: number;
  cost_bps?: number;
  lookback_years?: number;
}

export async function runMomentumBacktest(request: MomentumBacktestRequest): Promise<PairsBacktestResponse> {
  const { data } = await apiClient.post<PairsBacktestResponse>("/api/research-lab/momentum-backtest", request);
  return data;
}

// --- Forward validation gate ----------------------------------------------

export interface ForwardValidationRegisterRequest {
  ticker_a: string;
  ticker_b: string;
  fit_window_days?: number;
  entry_z?: number;
  exit_z?: number;
  cost_bps?: number;
}

export interface MomentumForwardValidationRegisterRequest {
  ticker: string;
  fit_window_days?: number;
  entry_z?: number;
  exit_z?: number;
  cost_bps?: number;
}

export type ForwardValidationStatus = "in_progress" | "forward_validated";

export interface ForwardValidationRegistrationOut {
  id: number;
  strategy_name: string;
  ticker_a: string;
  ticker_b: string;
  fit_window_days: number;
  entry_z: number;
  exit_z: number;
  cost_bps: number;
  status: ForwardValidationStatus;
  started_at: string;
  last_processed_date: string | null;
  n_forward_trading_days: number;
  min_trading_days_threshold: number;
  graduated_at: string | null;
  open_position: "long_spread" | "short_spread" | "long" | "short" | "flat";
  pct_days_mean_reverting_forward: number | null;
  sharpe_forward_so_far: number | null;
}

export interface ForwardValidationRegisterResponse extends ForwardValidationRegistrationOut {
  created: boolean;
}

export async function registerForwardValidation(
  request: ForwardValidationRegisterRequest,
): Promise<ForwardValidationRegisterResponse> {
  const { data } = await apiClient.post<ForwardValidationRegisterResponse>("/api/forward-validation", request);
  return data;
}

export async function registerMomentumForwardValidation(
  request: MomentumForwardValidationRegisterRequest,
): Promise<ForwardValidationRegisterResponse> {
  const { data } = await apiClient.post<ForwardValidationRegisterResponse>(
    "/api/forward-validation/momentum",
    request,
  );
  return data;
}

export async function listForwardValidationRegistrations(): Promise<ForwardValidationRegistrationOut[]> {
  const { data } = await apiClient.get<ForwardValidationRegistrationOut[]>("/api/forward-validation");
  return data;
}

export async function deleteForwardValidationRegistration(id: number): Promise<void> {
  await apiClient.delete(`/api/forward-validation/${id}`);
}

// --- Research lab: parameter sweeps + leaderboard --------------------------

export interface SweepGridSpec {
  fit_window_days: number[];
  entry_z: number[];
  exit_z: number[];
  cost_bps: number[];
}

export interface SweepJobCreateRequest {
  ticker_a: string;
  ticker_b: string;
  lookback_years?: number;
  grid: SweepGridSpec;
}

export interface MomentumSweepJobCreateRequest {
  ticker: string;
  lookback_years?: number;
  grid: SweepGridSpec;
}

export type SweepJobStatus = "queued" | "running" | "completed";

export interface SweepJobOut {
  id: number;
  strategy_name: string;
  ticker_a: string;
  ticker_b: string;
  lookback_years: number;
  grid: SweepGridSpec;
  total_configurations: number;
  configurations_completed: number;
  configurations_failed: number;
  status: SweepJobStatus;
  created_at: string;
  completed_at: string | null;
}

export async function createSweep(request: SweepJobCreateRequest): Promise<SweepJobOut> {
  const { data } = await apiClient.post<SweepJobOut>("/api/research-lab/sweeps", request);
  return data;
}

export async function createMomentumSweep(request: MomentumSweepJobCreateRequest): Promise<SweepJobOut> {
  const { data } = await apiClient.post<SweepJobOut>("/api/research-lab/sweeps/momentum", request);
  return data;
}

export async function listSweeps(): Promise<SweepJobOut[]> {
  const { data } = await apiClient.get<SweepJobOut[]>("/api/research-lab/sweeps");
  return data;
}

export type ExperimentRunSortBy =
  | "sharpe_net"
  | "sharpe_gross"
  | "max_drawdown_net"
  | "num_trades"
  | "win_rate"
  | "computed_at";
export type SortDirection = "asc" | "desc";

export interface ExperimentRunSummaryOut {
  id: number;
  strategy_name: string;
  ticker_a: string;
  ticker_b: string;
  status: PairsBacktestStatus;
  computed_at: string;
  fit_window_days: number;
  entry_z: number;
  exit_z: number;
  cost_bps: number;
  lookback_years: number;
  num_trades: number;
  sharpe_net: number | null;
  sharpe_gross: number | null;
  max_drawdown_net: number | null;
  win_rate: number | null;
  sweep_id: number | null;
  configurations_tested: number;
  n_trials_same_setup: number;
}

export interface ExperimentRunLeaderboardResponse {
  results: ExperimentRunSummaryOut[];
  total_matching: number;
  limit: number;
  offset: number;
}

export interface ExperimentRunListParams {
  sort_by?: ExperimentRunSortBy;
  sort_dir?: SortDirection;
  ticker_a?: string;
  ticker_b?: string;
  strategy_name?: string;
  sweep_id?: number;
  status?: PairsBacktestStatus;
  limit?: number;
  offset?: number;
}

export async function listExperimentRuns(
  params: ExperimentRunListParams,
): Promise<ExperimentRunLeaderboardResponse> {
  const { data } = await apiClient.get<ExperimentRunLeaderboardResponse>(
    "/api/research-lab/experiment-runs",
    { params },
  );
  return data;
}

export async function getExperimentRunDetail(id: number): Promise<PairsBacktestResponse> {
  const { data } = await apiClient.get<PairsBacktestResponse>(`/api/research-lab/experiment-runs/${id}`);
  return data;
}

// --- Research lab: systematic candidate screening ---------------------------

export type ScreeningStrategyName = "ou_pairs_v1" | "momentum_v1";
export type ScreeningJobStatus = "queued" | "running" | "completed" | "failed";

export interface ScreeningJobCreateRequest {
  strategy_name: ScreeningStrategyName;
}

export interface ScreeningCandidateOut {
  ticker_a: string;
  ticker_b: string;
  score: number;
  direction: "long" | "short" | null;
  regime: "trending" | "mean_reverting" | "indeterminate" | null;
  discovered_at: string;
}

export interface ScreeningJobOut {
  id: number;
  strategy_name: string;
  universe_size: number;
  n_tickers_resolved: number;
  n_candidates_found: number;
  status: ScreeningJobStatus;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  is_system: boolean;
}

export interface ScreeningJobDetailOut extends ScreeningJobOut {
  candidates: ScreeningCandidateOut[];
  methodology_note: string;
}

export async function createScreeningJob(request: ScreeningJobCreateRequest): Promise<ScreeningJobOut> {
  const { data } = await apiClient.post<ScreeningJobOut>("/api/research-lab/screening", request);
  return data;
}

export async function listScreeningJobs(): Promise<ScreeningJobOut[]> {
  const { data } = await apiClient.get<ScreeningJobOut[]>("/api/research-lab/screening");
  return data;
}

export async function getScreeningJob(id: number): Promise<ScreeningJobDetailOut> {
  const { data } = await apiClient.get<ScreeningJobDetailOut>(`/api/research-lab/screening/${id}`);
  return data;
}
