/** Honest wording for where a number comes from. One place so every page says the same thing. */
export type ModelKind = 'baseline' | 'trained' | 'rules' | 'unknown';

export function modelProvenance(p: string | null | undefined): { kind: ModelKind; label: string; short: string; detail: string } {
  const v = (p ?? '').toLowerCase();
  if (v.startsWith('district-trained')) {
    const ver = (p ?? '').replace(/^district-trained\s*/i, '').trim();
    return {
      kind: 'trained', label: `Trained on real sales${ver ? ` (${ver})` : ''}`, short: 'Trained on real sales',
      detail: 'This model was retrained on real ticket-sales history that was imported and checked. Estimates still carry uncertainty, but they reflect observed sell-through.',
    };
  }
  if (v === 'synthetic-baseline') {
    return {
      kind: 'baseline', label: 'Baseline estimate — not trained on real sales', short: 'Baseline estimate',
      detail: 'LiveIQ has no ticket-sales history, so this model is trained on a synthetic baseline built from public signals and industry rules of thumb. Treat fill-rate figures as a rough direction, not a forecast. Import real sales to replace it.',
    };
  }
  if (v === 'rule-based') {
    return {
      kind: 'rules', label: 'Rule-based estimate', short: 'Rule-based',
      detail: 'The trained model was unavailable for this request, so a fixed set of rules (public demand signals, city price level, season) produced this figure. It is not learned from sales.',
    };
  }
  return { kind: 'unknown', label: 'Estimate', short: 'Estimate', detail: 'The source of this estimate was not reported by the API. Treat it as indicative.' };
}

export const isBaseline = (p: string | null | undefined) => modelProvenance(p).kind !== 'trained';

/** Round a fill-rate to the nearest 5 when it is only a baseline estimate (no false precision). */
export const softFill = (v: number | null | undefined, baseline: boolean) =>
  v == null ? null : baseline ? Math.round(v / 5) * 5 : Math.round(v);

export function sourcesNote(c: number | null | undefined): string | null {
  if (c == null) return null;
  const n = Math.round(c * 4);
  return n >= 4 ? null : `Based on ${n} of 4 sources`;
}

/** 'Wikidata · 2026-11-08' / 'Manual · you' for a data_provenance entry. */
export function provenanceLabel(p: { source: string; by?: string; at?: string }, me?: string | null): string {
  const src = p.source === 'manual' ? 'Manual' : p.source.charAt(0).toUpperCase() + p.source.slice(1);
  const detail = p.source === 'manual'
    ? (p.by && me && p.by.toLowerCase() === me.toLowerCase() ? 'you' : p.by ?? '')
    : (p.at ?? '').slice(0, 10);
  return [src, detail].filter(Boolean).join(' · ');
}

// ── v3 score cues ─────────────────────────────────────────────────────────────
/** 'Based on 3 verified sources' from the v3 signals_used list (null for legacy rows / unrated). */
export function verifiedNote(signals: string[] | null | undefined): string | null {
  if (!signals || signals.length === 0) return null;
  return `Based on ${signals.length} verified source${signals.length === 1 ? '' : 's'}`;
}
export const LOW_CONFIDENCE = 0.5;
export const isLowConfidence = (c: number | null | undefined) => c != null && c < LOW_CONFIDENCE;

export interface SignalLine { key: string; label: string; used: boolean; text: string }
const YT_OK: Record<string, string> = {
  verified_wikidata: 'YouTube verified via Wikidata', verified_musicbrainz: 'YouTube verified via MusicBrainz',
  verified_wikidata_handle: 'YouTube verified via Wikidata handle', verified_manual: 'YouTube set manually by an analyst',
};
const YT_NO: Record<string, string> = {
  unresolved: 'YouTube channel not identified, so it is not used',
  title_mismatch: 'YouTube channel name does not match, so it is not used',
  metric_from_other_channel: 'Stored YouTube count belonged to a different channel, so it is not used',
  name_match_unverified: 'YouTube channel matched by name only, so it is not used',
};
const NOUN: Record<string, string> = { sports_team: 'teams', movie: 'films', comedian: 'comedians', attraction: 'festivals and venues', festival: 'festivals', theatre_group: 'theatre groups' };

/** Plain-language verdict per signal for the entity detail sheet. Pure; backed by signal_validity + score signals. */
export function describeSignals(args: {
  validity?: { youtube?: string | null; lastfm?: string | null } | null; entityType?: string | null; signalsUsed?: string[] | null;
  trendsBasis?: string | null; newsConfidence?: string | null; wikiViews?: number | null;
}): SignalLine[] {
  const { validity: v, entityType, signalsUsed, trendsBasis, newsConfidence, wikiViews } = args;
  const used = new Set(signalsUsed ?? []);
  const out: SignalLine[] = [];
  const yt = v?.youtube ?? null;
  out.push({ key: 'youtube', label: 'YouTube', used: used.has('youtube'), text: yt == null ? 'Not checked yet' : YT_OK[yt] ?? YT_NO[yt] ?? `YouTube: ${yt.replace(/_/g, ' ')}` });
  const lf = v?.lastfm ?? null;
  const lfText = lf == null ? 'Not checked yet'
    : lf === 'wrong_type' ? `Last.fm not applicable to ${NOUN[entityType ?? ''] ?? 'this type of entity'}`
    : lf === 'verified_mbid' ? 'Last.fm verified via MusicBrainz'
    : lf === 'name_verified_tags' ? 'Last.fm matched by name and genre tags (weaker proof)'
    : lf === 'unresolved' ? 'Last.fm artist not found, so it is not used'
    : lf === 'name_unverified' ? 'Last.fm name match could not be verified, so it is not used' : `Last.fm: ${lf.replace(/_/g, ' ')}`;
  out.push({ key: 'lastfm', label: 'Last.fm', used: used.has('lastfm'), text: lfText });
  out.push({ key: 'wiki', label: 'Wikipedia', used: used.has('wiki'), text: wikiViews != null ? 'Wikipedia article found via Wikidata' : 'No Wikipedia article linked' });
  out.push({ key: 'trends', label: 'Google Trends', used: used.has('trends'),
    text: trendsBasis === 'topic' ? 'Google Trends measured by exact topic' : trendsBasis === 'term' ? 'Google Trends measured by search term (name is unambiguous)'
      : 'Google Trends skipped: the name is ambiguous or not yet measured' });
  out.push({ key: 'news', label: 'News', used: used.has('news'),
    text: newsConfidence === 'strict' ? 'News counted from headlines that name the entity in context' : newsConfidence === 'generic_filtered'
      ? 'News counted with extra-strict filtering (generic name)' : newsConfidence === 'ambiguous_skipped' ? 'News skipped: generic name, no headline passed the strict filter'
      : 'News not yet strictly filtered, so it is not used' });
  return out;
}
