import axios, { isAxiosError } from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  const wsProtocol = API_BASE_URL.startsWith("https") ? "wss" : "ws";
  const host = API_BASE_URL.replace(/^https?:\/\//, "");
  return `${wsProtocol}://${host}/ws/live-quotes`;
}

// --- Auth ---------------------------------------------------------------

export interface UserOut {
  id: number;
  email: string;
}

export async function registerUser(email: string, password: string): Promise<UserOut> {
  const { data } = await apiClient.post<UserOut>("/api/auth/register", { email, password });
  return data;
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
