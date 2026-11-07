const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ── Token storage ────────────────────────────────────────────────
// localStorage (not cookies) — this is a client-rendered SPA-style app with
// no server-side rendering that needs the token, so there's no CSRF surface
// that cookie storage would help with; XSS is the relevant threat either way.
const ACCESS_TOKEN_KEY = 'liveiq_access_token';
const REFRESH_TOKEN_KEY = 'liveiq_refresh_token';

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// Serializes concurrent refresh attempts so a burst of 401s (e.g. several
// SWR hooks firing at once) triggers exactly one refresh call, not N.
let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function apiFetch<T>(path: string, opts?: RequestInit, _isRetry = false): Promise<T> {
  const token = getAccessToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...opts,
  });

  if (res.status === 401 && !_isRetry && !path.startsWith('/auth/')) {
    const refreshed = await tryRefresh();
    if (refreshed) return apiFetch<T>(path, opts, true);
    clearTokens();
    if (typeof window !== 'undefined') window.location.href = '/login';
    throw new Error('Session expired — please log in again');
  }

  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────
export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_verified: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

interface AuthResponse {
  user: AuthUser;
  tokens: { access_token: string; refresh_token: string; token_type: string };
}

export async function login(req: LoginRequest): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Login failed (${res.status})`);
  }
  const data: AuthResponse = await res.json();
  setTokens(data.tokens.access_token, data.tokens.refresh_token);
  return data;
}

export async function register(req: RegisterRequest): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Registration failed (${res.status})`);
  }
  const data: AuthResponse = await res.json();
  setTokens(data.tokens.access_token, data.tokens.refresh_token);
  return data;
}

export const getMe = () => apiFetch<AuthUser>('/auth/me');

// Best-effort — the backend call revokes every refresh token for this
// user (bumps token_version), but tokens are cleared client-side either
// way so the user is logged out locally even if this request fails
// (offline, backend down, token already expired).
export async function logoutRemote(): Promise<void> {
  const token = getAccessToken();
  if (!token) return;
  try {
    await fetch(`${BASE}/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // ignored — see comment above
  }
}

// ── System / Health ────────────────────────────────────────────
export const getHealth = () => apiFetch<HealthResponse>('/health');

// ── Notifications ────────────────────────────────────────────────
export const getNotifications = (unreadOnly?: boolean) =>
  apiFetch<NotificationsResponse>(`/notifications${unreadOnly ? '?unread_only=true' : ''}`);
export const getUnreadCount = () => apiFetch<{ unread_count: number }>('/notifications/unread-count');
export const markNotificationRead = (id: string) =>
  apiFetch<{ status: string; id: string }>(`/notifications/${id}/read`, { method: 'POST' });
export const markAllNotificationsRead = () =>
  apiFetch<{ status: string; marked_read: number }>('/notifications/read-all', { method: 'POST' });

// ── Global entity search (Topbar) ────────────────────────────────
export interface EntitySearchResult {
  id: string;
  name: string;
  entity_type: string;
  category: string | null;
  is_international: boolean;
}
export const searchEntities = (q: string, limit = 6) =>
  apiFetch<{ results: EntitySearchResult[]; total: number }>(`/entities/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// ── Executive ──────────────────────────────────────────────────
export const getKPIs          = () => apiFetch<KPIResponse>('/executive/kpis');
export const getBriefing      = () => apiFetch<BriefingResponse>('/executive/briefing');
export const getPortfolio     = (type?: string) =>
  apiFetch<PortfolioResponse>(`/executive/portfolio${type ? `?entity_type=${type}` : ''}`);

// Returns a Blob (not JSON) — caller is responsible for triggering the
// browser download via a temporary object URL. The endpoint synchronously
// calls Groq for the AI briefing plus several DB queries, so it can
// legitimately take a few seconds — but a hung Groq call shouldn't leave
// the UI stuck forever, hence the explicit timeout.
export async function downloadExecutiveReportPdf(): Promise<Blob> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000);
  try {
    const token = getAccessToken();
    const res = await fetch(`${BASE}/executive/report/pdf`, {
      signal: controller.signal,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.status === 401) {
      const refreshed = await tryRefresh();
      if (refreshed) {
        const retryToken = getAccessToken();
        const retryRes = await fetch(`${BASE}/executive/report/pdf`, {
          signal: controller.signal,
          headers: retryToken ? { Authorization: `Bearer ${retryToken}` } : {},
        });
        if (!retryRes.ok) throw new Error(`API ${retryRes.status}: ${retryRes.statusText}`);
        return await retryRes.blob();
      }
      clearTokens();
      if (typeof window !== 'undefined') window.location.href = '/login';
      throw new Error('Session expired — please log in again');
    }
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
    return await res.blob();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Report generation timed out after 60s. Try again — the AI briefing step may be slow.');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Dashboard ──────────────────────────────────────────────────
export const getDashboardSummary = () => apiFetch<DashboardSummary>('/dashboard/summary');
export const getDashboardAlerts  = () => apiFetch<AlertsResponse>('/dashboard/alerts');

// ── Cities ─────────────────────────────────────────────────────
export const getCities        = (tier?: number) =>
  apiFetch<CitiesResponse>(`/cities/${tier ? `?tier=${tier}` : ''}`);
export const getTopCities     = () => apiFetch<CitiesResponse>('/cities/top');
export const getCityGaps      = () => apiFetch<GapsResponse>('/cities/gaps');
export const getCityIntel     = (city: string) =>
  apiFetch<CityIntelResponse>(`/cities/${encodeURIComponent(city)}/intelligence`);
// Alias used by the Markets page
export const getCityIntelligence = getCityIntel;
export const getCityVenues    = (city: string) =>
  apiFetch<CityVenuesResponse>(`/cities/${encodeURIComponent(city)}/venues`);

// ── Competitors ────────────────────────────────────────────────
export const getCompetitorIntel = (city?: string) =>
  apiFetch<CompetitorIntelResponse>(`/competitors/intelligence${city ? `?city=${city}` : ''}`);
export const getCompetitorGaps  = () => apiFetch<any>('/competitors/gaps');
export const getActivityFeed    = () => apiFetch<any>('/competitors/activity-feed');

// ── Pricing ────────────────────────────────────────────────────
export const optimizePrice = (body: PricingRequest) =>
  apiFetch<PricingResponse>('/pricing/optimize', { method: 'POST', body: JSON.stringify(body) });
export const getPriceBenchmarks = () => apiFetch<any>('/pricing/benchmarks');

// ── Social Listening (M7) ──────────────────────────────────────
export const getEntitySentiment = (entityId: string) =>
  apiFetch<any>(`/social/sentiment/${entityId}`);
export const getEntityTopics = (entityId: string, days?: number) =>
  apiFetch<any>(`/social/topics/${entityId}${days ? `?days=${days}` : ''}`);
export const getCrisisAlerts = () => apiFetch<any>('/social/crisis-alerts');

// ── AI Recommendation (M6) ──────────────────────────────────────
export const getRecommendedEntities = (params?: { category?: string; city?: string; limit?: number }) => {
  const q = new URLSearchParams();
  if (params?.category) q.set('category', params.category);
  if (params?.city) q.set('city', params.city);
  if (params?.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  return apiFetch<any>(`/recommend/entities${qs ? `?${qs}` : ''}`);
};
export const getSignRecommendation = (body: { entity_id: string; city: string; venue_capacity: number; proposed_price: number; category?: string }) =>
  apiFetch<any>('/recommend/sign', { method: 'POST', body: JSON.stringify(body) });

// ── Psychological Demand Analysis ──────────────────────────────
export const getPsychologyReport = (entityId: string, city?: string) =>
  apiFetch<any>(`/psychology/${entityId}${city ? `?city=${encodeURIComponent(city)}` : ''}`);
export const getPriceElasticity = (entityId: string, price?: number) =>
  apiFetch<any>(`/pricing/elasticity/${entityId}${price ? `?proposed_price=${price}` : ''}`);

// ── Event Deal Modeler ───────────────────────────────────────────
export const modelEventDeal = (body: DealModelRequest) =>
  apiFetch<DealModelResponse>('/events/model', { method: 'POST', body: JSON.stringify(body) });

// ── Artist Pairing Recommender ────────────────────────────────────
export const recommendPairs = (body: PairRecommendRequest) =>
  apiFetch<PairRecommendResponse>('/intelligence/pair-recommend', { method: 'POST', body: JSON.stringify(body) });

// ── Demand Forecasting ────────────────────────────────────────────
export const getDemandForecast = (entityId: string, opts?: { city?: string; months?: number }) => {
  const params = new URLSearchParams();
  if (opts?.city) params.set('city', opts.city);
  if (opts?.months) params.set('months', String(opts.months));
  const qs = params.toString();
  return apiFetch<DemandForecastResponse>(`/intelligence/${entityId}/forecast${qs ? `?${qs}` : ''}`);
};

// ── Venue Availability Calendar ────────────────────────────────────
export const getVenueCalendar = (venueId: string, months?: number) =>
  apiFetch<VenueCalendarResponse>(`/venues/${venueId}/calendar${months ? `?months=${months}` : ''}`);

// ── Watchlist ─────────────────────────────────────────────────────
export const getWatchlist = () => apiFetch<WatchlistResponse>('/watchlist');
export const addToWatchlist = (entityId: string) =>
  apiFetch<{ status: string; entity_id: string; already_watched: boolean }>(`/watchlist/${entityId}`, { method: 'POST' });
export const removeFromWatchlist = (entityId: string) =>
  apiFetch<{ status: string; entity_id: string }>(`/watchlist/${entityId}`, { method: 'DELETE' });

// ─── Types ────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  type: string;
  title: string | null;
  message: string | null;
  entity: string | null;
  severity: 'low' | 'medium' | 'high' | 'critical';
  is_read: boolean;
  is_watched: boolean;
  detected_at: string | null;
}

// ── Venue Availability Calendar ────────────────────────────────────
export interface VenueCalendarEvent {
  id: string;
  title: string;
  event_date: string;
  status: string | null;
  source: string | null;
}

export interface VenueCalendarWeek {
  week_start: string;
  week_end: string;
  events_this_week: VenueCalendarEvent[];
  weekend_events: VenueCalendarEvent[];
  is_weekend_booked: boolean;
  is_booked: boolean;
}

export interface VenueCalendarResponse {
  venue: { id: string; name: string; city: string; capacity: number | null };
  range: { start: string; end: string; months: number };
  weeks: VenueCalendarWeek[];
  summary: {
    total_weeks: number;
    booked_weekends: number;
    open_weekends: number;
    total_tracked_events: number;
  };
  data_note?: string;
}

export interface BriefingResponse {
  briefing: string;
  generated_at: string;
  data_context: { entities_analyzed: number; active_cities: number; model: string };
}

export interface PortfolioResponse {
  portfolio: PortfolioEntity[];
  total: number;
  with_scores: number;
  health_summary: { strong: number; good: number; needs_data: number; weak: number };
}

export interface PortfolioEntity {
  rank: number; id: string; name: string; type: string; category: string;
  country: string; is_international: boolean; composite_score: number | null;
  google_trend_score: number | null; news_mentions_7d: number | null;
  health: string; last_updated: string | null;
}

export interface CitiesResponse { cities: CityItem[]; total: number; }

export interface CityItem {
  id: string; name: string; state: string;
  tier?: number; district_tier?: number;
  scores?: { composite: number; music: number; nightlife: number; sports: number; arts: number; comedy: number };
  // Some endpoints flatten scores to the top level
  music_score?: number; nightlife_score?: number; sports_score?: number;
  active_on_district?: boolean; population?: number; metro_population?: number;
  avg_monthly_income?: number; top_categories?: string[];
}

export interface CityVenuesResponse {
  city: string;
  venues: {
    // id is null for Ticketmaster-fallback venues (not real venue-table
    // rows) — always present as a key, but not always a usable value.
    id: string | null; name: string; capacity: number | null; type: string | null;
    categories: string[]; avg_fill_rate: number | null; avg_ticket_price: number | null;
    rating: number | null;
  }[];
  total: number;
  source: 'database' | 'ticketmaster' | 'none';
}

export interface GapsResponse { gaps: any[]; total: number; }
export interface CityIntelResponse { city: any; intelligence: any; }
export interface CompetitorIntelResponse { city: string; platforms: any[]; event_activity: any; }

export interface PricingRequest {
  entity_id: string; city: string; venue_capacity: number;
  proposed_price: number; category?: string; event_date_month?: number;
}

export interface PricingResponse {
  entity: any; recommendation: any; signals: any; benchmarks: any;
}

// ── Event Deal Modeler ───────────────────────────────────────────

export interface DealModelRequest {
  entity_id: string;
  city: string;
  venue_id?: string;
  venue_capacity?: number;
  ticket_price: number;
  lead_days?: number;
}

export interface DealScenario {
  fill_rate_pct: number;
  attendance: number;
  gross_revenue: number;
  gross_revenue_fmt: string;
  artist_fee: number;
  venue_cost: number;
  ops_cost: number;
  total_cost: number;
  net_profit: number;
  net_profit_fmt: string;
  margin_pct: number | null;
}

export interface DealModelResponse {
  entity: {
    id: string; name: string; category: string | null;
    is_international: boolean; composite_score: number; has_live_metrics: boolean;
  };
  venue: { id: string | null; name: string | null; city: string; capacity: number };
  inputs: { ticket_price: number; lead_days: number };
  prediction: { predicted_fill_rate_pct: number; model: string; confidence_pct: number; model_data_source: string | null };
  artist_fee: {
    amount: number; amount_fmt: string;
    range_min: number | null; range_max: number | null; source: string;
  };
  scenarios: { conservative: DealScenario; expected: DealScenario; optimistic: DealScenario };
  break_even: { tickets: number | null; fill_rate_pct: number | null; achievable: boolean };
  risk_level: 'Low' | 'Medium' | 'High';
  cost_model_note: string;
  market_context: {
    predicthq: {
      comparable_events_found: number;
      avg_rank: number | null;
      avg_predicted_attendance: number | null;
      source: string;
    };
  };
}

// ── Artist Pairing Recommender ────────────────────────────────────

export interface PairRecommendRequest {
  city: string;
  budget?: number;
  anchor_entity_id?: string;
  market?: string;
  limit?: number;
}

export interface PairRecommendation {
  entity_a: { id: string; name: string; category: string | null; composite_score: number | null };
  entity_b: { id: string; name: string; category: string | null; composite_score: number | null };
  shared_genres: string[];
  similarity_score: number;
  combined_booking_fee_estimate: number | null;
}

export interface PairRecommendResponse {
  city: string;
  budget: number | null;
  anchor_entity: { id: string; name: string } | null;
  candidates_considered: number;
  pairs_matching_genre: number;
  recommendations: PairRecommendation[];
  methodology: string;
}

// ── Demand Forecasting ────────────────────────────────────────────

export interface ForecastHistoryPoint {
  date: string;
  google_trend_score: number;
}

export interface ForecastPoint {
  date: string;
  predicted_trend_score: number;
  lower_bound: number;
  upper_bound: number;
}

export interface DemandForecastResponse {
  entity: { id: string; name: string };
  city: string | null;
  status: 'ok' | 'insufficient_history';
  history: ForecastHistoryPoint[];
  history_points: number;
  history_span_days: number;
  minimum_required?: { points: number; span_days: number };
  trend_direction?: 'rising' | 'falling' | 'stable';
  forecast: ForecastPoint[] | null;
  message?: string;
  methodology?: string;
}

// ── Dashboard ─────────────────────────────────────────────────

export interface DashboardHero {
  total_entities: number;
  entities_with_metrics: number;
  total_cities: number;
  active_cities: number;
  expansion_targets: number;
  total_events: number;
  international_acts: number;
  avg_composite_score: number | null;
}

export interface TrendingEntity {
  id: string;
  name: string;
  type: string;
  category: string | null;
  country: string;
  is_international: boolean;
  composite_score: number;
  google_trend: number | null;
  news_mentions_7d: number | null;
  listeners: number | null;
}

export interface CityHeatItem {
  city: string;
  tier: number;
  music_score: number | null;
  nightlife_score: number | null;
  active_on_district: boolean;
}

export interface UpcomingEvent {
  id: string;
  name: string;
  city: string | null;
  venue: string | null;
  event_date: string | null;
  category: string | null;
  min_price: number | null;
  max_price: number | null;
  source: string | null;
}

export interface CategoryBreakdown {
  category: string;
  count: number;
}

export interface DashboardSummary {
  generated_at: string;
  hero: DashboardHero;
  trending_entities: TrendingEntity[];
  city_heat: CityHeatItem[];
  upcoming_events: UpcomingEvent[];
  category_breakdown: CategoryBreakdown[];
  type_breakdown: { type: string; count: number }[];
}

export interface DashboardAlert {
  type: 'breakout' | 'buzz' | 'opportunity' | 'info';
  title: string;
  message: string;
  entity: string | null;
  category: string | null;
  severity: 'high' | 'medium' | 'low';
  ts: string;
}

export interface AlertsResponse {
  alerts: DashboardAlert[];
  total: number;
  generated_at: string;
}

// ── Dashboard (market-scoped) ─────────────────────────────────────
export const getDashboardSummaryScoped = (market: 'india' | 'global' | 'all' = 'all') =>
  apiFetch<DashboardSummary>(`/dashboard/summary?market=${market}`);

// ── Trend Radar / Intelligence (market-scoped) ───────────────────
export interface BreakoutPrediction {
  entity_id: string; name: string; entity_type: string; category: string | null; country: string | null;
  composite_score: number | null; trend_direction: 'rising' | 'falling' | 'stable' | 'pending';
  lastfm_listeners?: number | null; news_mentions_7d: number | null; google_trend_score: number | null; last_updated: string | null;
}
export interface BreakoutResponse { predictions: BreakoutPrediction[]; total: number; has_live_scores: boolean; note?: string }
export interface ViralSignal {
  entity_id: string; name: string; entity_type: string; news_mentions_7d: number | null;
  google_trend_score: number | null; composite_score: number | null; sentiment_compound: number | null;
}
export interface ViralResponse { signals: ViralSignal[]; total?: number; message?: string }
export const getTrendBreakouts = (market: 'india' | 'global' | 'all' = 'all', limit = 24) =>
  apiFetch<BreakoutResponse>(`/trends/breakout?market=${market}&limit=${limit}`);
export const getTrendViral = (market: 'india' | 'global' | 'all' = 'all', limit = 12) =>
  apiFetch<ViralResponse>(`/trends/viral?market=${market}&limit=${limit}`);

export interface EntityScoreResponse {
  entity_id: string; entity_name: string; composite_score: number | null; trend_direction: string;
  signals: { lastfm_listeners?: number | null; youtube_subscribers?: number | null; youtube_views_30d?: number | null;
    news_mentions_7d?: number | null; google_trend_score?: number | null; google_trend_delta_7d?: number | null;
    sentiment_compound?: number | null; data_completeness?: number | null };
  last_updated: string | null; data_sources: string[]; message?: string;
}
export const getEntityScore = (entityId: string) => apiFetch<EntityScoreResponse>(`/entities/${entityId}/score`);
export interface EntityCityDemand { city: string; state: string | null; tier: number | null; demand_score: number; is_home_city: boolean; active_on_district: boolean; demand_rank: number }
export const getEntityCities = (entityId: string) =>
  apiFetch<{ entity_id: string; entity_name: string; cities: EntityCityDemand[]; methodology: string }>(`/entities/${entityId}/cities`);
export interface CompareProfile {
  id: string; name: string; entity_type: string; category: string | null; country: string | null; is_international: boolean;
  home_city?: string | null; primary_market?: string | null; booking_price_range_min?: number | null; booking_price_range_max?: number | null;
  typical_venue_capacity_min?: number | null; typical_venue_capacity_max?: number | null;
  composite_score: number | null; trend_direction: string; listeners: number | null;
}
export const compareEntities = (ids: string[]) =>
  apiFetch<{ entities: CompareProfile[]; comparison_count: number }>('/entities/compare', { method: 'POST', body: JSON.stringify(ids) });


// ══ Typed additions (markets / competitors / calendar / pricing pages) ══════════

/** Error carrying HTTP status + backend `detail`, so UIs can show friendly 403/422 messages. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) { super(detail); this.status = status; this.detail = detail; }
}

async function apiFetchStrict<T>(path: string, opts?: RequestInit, retried = false): Promise<T> {
  const token = getAccessToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...opts,
  });
  if (res.status === 401 && !retried && (await tryRefresh())) return apiFetchStrict<T>(path, opts, true);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j?.detail === 'string') detail = j.detail;
      else if (Array.isArray(j?.detail)) detail = j.detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ');
    } catch { /* non-JSON body */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export interface CompetitorPlatform {
  name: string; parent: string; founded: number; strengths: string[]; markets: string[];
  active_in_city: boolean; market_position: string; news_mentions_7d: number;
  estimated_events?: number; live_events_count?: number;
}
export interface CompetitorIntelligence {
  city: string; total_ticketmaster_events_live: number;
  platforms: Record<string, CompetitorPlatform>;
  district_opportunity: { city_tier: number | string; district_active: boolean; recommendation: string };
  data_sources: string[]; note?: string;
}
export const getCompetitorIntelligence = (city: string) =>
  apiFetchStrict<CompetitorIntelligence>(`/competitors/intelligence?city=${encodeURIComponent(city)}`);

export interface CompetitorGapItem {
  city: string; state: string | null; tier: number; population: number | null; avg_event_market_score: number;
  competitor_presence: { bookmyshow: string; insider: string; district: string };
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}
export interface CompetitorGapsResponse { gaps: CompetitorGapItem[]; total: number; high_priority: number; insight?: string }
export const getCompetitorGapList = () => apiFetchStrict<CompetitorGapsResponse>('/competitors/gaps');

export interface CompetitorArticle { platform: string; title: string | null; source: string | null; published_at: string | null; url: string | null }
export interface CompetitorFeedResponse { articles: CompetitorArticle[]; total: number; platforms_monitored: string[]; note?: string }
export const getCompetitorFeed = (limit = 20) => apiFetchStrict<CompetitorFeedResponse>(`/competitors/activity-feed?limit=${limit}`);

export interface CityScores { nightlife: number | null; sports_affinity: number | null; arts_culture: number | null; comedy_market: number | null; music_market: number | null; composite: number | null }
export interface MarketCity {
  id: string; name: string; state: string; tier: number; population: number | null; metro_population: number | null;
  avg_monthly_income: number | null; youth_population_pct: number | null; top_categories: string[] | null;
  active_on_district: boolean; scores: CityScores;
}
export const getMarketCities = () => apiFetchStrict<{ cities: MarketCity[]; total: number }>('/cities/');

export interface CityIntelDetail extends MarketCity {
  festival_months?: { festivals?: Record<string, number>; low_demand?: number[]; high_demand?: number[] } | null;
  intelligence: {
    expansion_recommendation: string; peak_season_months: string[]; monsoon_risk: string; income_tier: string; youth_index: string;
    restaurant_partnerships: { name: string; venue_type: string | null; cuisine: string | null }[];
    venue_counts_by_type: Record<string, number>;
  };
}
export const getMarketCityIntel = (city: string) => apiFetchStrict<CityIntelDetail>(`/cities/${encodeURIComponent(city)}/intelligence`);

export interface CityRestaurant {
  id: string; name: string; venue_type: string | null; cuisines: string[]; address: string | null;
  latitude: number | null; longitude: number | null; phone: string | null; website: string | null; sources: string[];
}
export const getCityRestaurants = (city: string, o: { venue_type?: string; cuisine?: string; limit?: number } = {}) => {
  const q = new URLSearchParams({ limit: String(o.limit ?? 100) });
  if (o.venue_type) q.set('venue_type', o.venue_type);
  if (o.cuisine) q.set('cuisine', o.cuisine);
  return apiFetchStrict<{ city: string; restaurants: CityRestaurant[]; total: number; data_note?: string }>(`/cities/${encodeURIComponent(city)}/restaurants?${q}`);
};

export const getVenueCalendarStrict = (venueId: string, months = 3) =>
  apiFetchStrict<VenueCalendarResponse>(`/venues/${venueId}/calendar?months=${months}`);
export const getCityVenuesStrict = (city: string) => apiFetchStrict<CityVenuesResponse>(`/cities/${encodeURIComponent(city)}/venues`);

export interface PricingResult {
  entity: { id: string; name: string; type: string | null; category: string | null; is_international: boolean };
  recommendation: {
    proposed_price: number; recommended_price: number; price_tier: string; confidence: string; reasoning: string;
    predicted_fill_rate: number | null; sensitivity_curve: { price: number; attendance_pct: number }[];
  };
  signals: { composite_score: number; google_trend_score: number; demand_score: number; city_multiplier: number; capacity_factor: number; season_factor: number; international_factor: number };
  benchmarks: { category: string; floor: number; sweet_spot: number; premium: number; ultra_premium: number };
  model: string;
}
export const optimizePriceStrict = (body: PricingRequest) =>
  apiFetchStrict<PricingResult>('/pricing/optimize', { method: 'POST', body: JSON.stringify(body) });

export interface PriceBenchmarks {
  benchmarks: Record<string, { floor: number; sweet_spot: number; premium: number; ultra_premium: number }>;
  city_multipliers: Record<string, number>; notes?: Record<string, string>;
}
export const getPriceBenchmarkTable = () => apiFetchStrict<PriceBenchmarks>('/pricing/benchmarks');

export interface ElasticityPoint { city: string; tier: number; state: string; optimal_price: number; city_multiplier: number; demand_index: number; affordability_index: number }
export const getElasticityCurve = (entityId: string, price: number) =>
  apiFetchStrict<{ entity_name: string; proposed_price: number; elasticity_curve: ElasticityPoint[]; insight: string }>(`/pricing/elasticity/${entityId}?proposed_price=${price}`);

// ── Restored types (were dropped by a concurrent edit) ────────────
export interface WatchlistEntity {
  id: string;
  name: string;
  category: string | null;
  is_international: boolean;
  watched_since: string | null;
}
export interface WatchlistResponse { watchlist: WatchlistEntity[]; total: number }
export interface NotificationsResponse { notifications: NotificationItem[]; total: number }
export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  services: { postgres: 'up' | 'down'; mongodb: 'up' | 'down'; redis: 'up' | 'down' };
  apis_configured: Record<string, boolean>;
}
export interface KPIResponse {
  generated_at: string;
  entity_portfolio: {
    total_tracked: number; with_live_metrics: number; metrics_coverage_pct: number;
    avg_composite_score: number | null; by_type: Record<string, number>;
    top_categories: { category: string; count: number }[]; international: number; indian: number;
  };
  top_entities: { name: string; type: string; category: string; composite_score: number; google_trend: number; news_mentions_7d: number }[];
  city_coverage: { total_tracked: number; active_on_district: number; expansion_opportunities: number };
}

// ── Recommendations (market-aware) ───────────────────────────────
export interface RecommendationItem {
  entity_id: string; entity_name: string; entity_type: string; category: string | null; is_international: boolean;
  composite_score: number; city_demand_score: number | null; recommendation_score: number;
  trend_direction: 'rising' | 'falling' | 'stable'; last_updated: string | null; rank: number;
}
export interface RecommendationsResponse { recommendations: RecommendationItem[]; total_candidates: number; methodology: string }
export const getRankedRecommendations = (p: { category?: string; city?: string; isInternational?: boolean; excludeWatchlisted?: boolean; limit?: number }) => {
  const q = new URLSearchParams();
  if (p.category) q.set('category', p.category);
  if (p.city) q.set('city', p.city);
  if (p.isInternational != null) q.set('is_international', String(p.isInternational));
  if (p.excludeWatchlisted) q.set('exclude_watchlisted', 'true');
  q.set('limit', String(p.limit ?? 20));
  return apiFetch<RecommendationsResponse>(`/recommend/entities?${q.toString()}`);
};
export interface SignVerdictResponse {
  entity_id: string; entity_name: string; city: string; verdict: 'sign' | 'consider' | 'pass' | 'insufficient_data'; reasons: string[];
  predicted_fill_rate_pct: number; recommended_price: number; proposed_price: number; confidence: number; model: string;
  has_real_metrics: boolean; city_tracked: boolean;
}
export const getSignVerdict = (body: { entity_id: string; city: string; venue_capacity: number; proposed_price: number }) =>
  apiFetch<SignVerdictResponse>('/recommend/sign', { method: 'POST', body: JSON.stringify(body) });

// ── Copilot ──────────────────────────────────────────────────────
export interface CopilotModel { id: string; name: string; context_window: number; description: string; recommended: boolean }
export interface CopilotModelsResponse { current_model: string; available_models: CopilotModel[]; groq_configured: boolean }
export const getCopilotModels = () => apiFetch<CopilotModelsResponse>('/copilot/models');

// ── Psychology (typed) ───────────────────────────────────────────
export interface PsychologyFactor { name: string; multiplier: number; real_signal: Record<string, string | number | null>; explanation: string }
export interface PsychologyReport {
  entity_id: string; entity_name: string; city: string | null; combined_multiplier: number; interpretation: string;
  factors: PsychologyFactor[]; data_coverage_note?: string;
}
export const getPsychology = (entityId: string, city?: string) =>
  apiFetch<PsychologyReport>(`/psychology/${entityId}${city ? `?city=${encodeURIComponent(city)}` : ''}`);

// ── Social listening (typed) ─────────────────────────────────────
export interface SentimentResponse {
  entity_id: string; entity_name: string; status: 'ok' | 'no_data_yet'; message?: string;
  sentiment: { positive?: number | null; negative?: number | null; neutral?: number | null; compound?: number | null; sample_size?: number | null;
    reddit_posts_7d?: number | null; news_mentions_7d?: number | null; last_collected_at?: string | null };
  recent_posts: { platform: string; content_snippet: string; sentiment_label: string | null; sentiment_score: number | null; likes: number | null; comments: number | null; analyzed_at: string | null }[];
}
export interface TopicsResponse { entity_id: string; topics: { topic: string; mentions: number }[]; total_posts_analyzed: number; window_days: number; methodology?: string }
export interface CrisisAlert { entity_id: string; entity_name: string; severity: 'critical' | 'high' | 'medium'; negative_share_last_24h: number; negative_share_prior_7d: number; delta_pct_points: number; posts_last_24h: number }
export const getSentiment = (entityId: string) => apiFetch<SentimentResponse>(`/social/sentiment/${entityId}`);
export const getTopics = (entityId: string, days = 30) => apiFetch<TopicsResponse>(`/social/topics/${entityId}?days=${days}`);
export const getCrisis = () => apiFetch<{ alerts: CrisisAlert[]; total: number; methodology?: string }>('/social/crisis-alerts');
