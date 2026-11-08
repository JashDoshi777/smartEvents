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
