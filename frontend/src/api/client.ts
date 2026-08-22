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

export async function registerUser(email: string, password: string): Promise<RegisterResponse> {
  const { data } = await apiClient.post<RegisterResponse>("/api/auth/register", { email, password });
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

export type AlertRuleType = "price_move" | "risk_metric";
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
  portfolio_id: number;
  rule_type: AlertRuleType;
  ticker: string | null;
  metric: string | null;
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
  portfolio_id: number;
  rule_type: AlertRuleType;
  ticker?: string | null;
  metric?: string | null;
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
