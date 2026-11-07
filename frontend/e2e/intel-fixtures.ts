export const dealFixture = {
  entity: { id: 'e1', name: 'Arijit Singh', category: 'Music', is_international: false, composite_score: 72, has_live_metrics: true },
  venue: { id: 'v1', name: 'Jio World Garden', city: 'Mumbai', capacity: 9000 },
  inputs: { ticket_price: 2500, lead_days: 60 },
  prediction: { predicted_fill_rate_pct: 78, model: 'gradient-boost', confidence_pct: 64, model_data_source: 'District history' },
  artist_fee: { amount: 12000000, amount_fmt: '₹1.2 Cr', range_min: 8000000, range_max: 15000000, source: 'booking_price_range' },
  scenarios: {
    conservative: { fill_rate_pct: 58, attendance: 5220, gross_revenue: 13050000, artist_fee: 12000000, venue_cost: 1305000, ops_cost: 3262500, total_cost: 16567500, net_profit: -3517500, net_profit_fmt: '', margin_pct: -26.9 },
    expected: { fill_rate_pct: 78, attendance: 7020, gross_revenue: 17550000, artist_fee: 12000000, venue_cost: 1755000, ops_cost: 4387500, total_cost: 18142500, net_profit: -592500, net_profit_fmt: '', margin_pct: -3.4 },
    optimistic: { fill_rate_pct: 95, attendance: 8550, gross_revenue: 21375000, artist_fee: 12000000, venue_cost: 2137500, ops_cost: 5343750, total_cost: 19481250, net_profit: 1893750, net_profit_fmt: '', margin_pct: 8.9 },
  },
  break_even: { tickets: 7257, fill_rate_pct: 80.6, achievable: true },
  risk_level: 'Medium',
  cost_model_note: 'Venue (~10% of gross) and operations (~25%) are rule-of-thumb estimates.',
  market_context: { predicthq: { comparable_events_found: 4, avg_rank: 61, avg_predicted_attendance: 7400, source: 'predicthq' } },
};

export const forecastFixture = (n = 20) => {
  const start = Date.parse('2026-09-01');
  const history = Array.from({ length: n }, (_, i) => ({ date: new Date(start + i * 7 * 864e5).toISOString().slice(0, 10), google_trend_score: 50 + Math.round(20 * Math.sin(i / 3)) }));
  const fstart = start + n * 7 * 864e5;
  const forecast = Array.from({ length: 90 }, (_, i) => { const p = 62 + i * .1; return { date: new Date(fstart + i * 864e5).toISOString().slice(0, 10), predicted_trend_score: p, lower_bound: p - 8 - i * .05, upper_bound: p + 8 + i * .05 }; });
  return { entity: { id: 'e1', name: 'Divine' }, city: null, status: 'ok', history, history_points: n, history_span_days: n * 7, trend_direction: 'rising', forecast, methodology: 'Prophet on weekly Google Trends readings.' };
};

export function sseBody(chunks: string[]) {
  return chunks.map(c => `data: ${JSON.stringify({ chunk: c })}\n\n`).join('') + 'data: [DONE]\n\n';
}
