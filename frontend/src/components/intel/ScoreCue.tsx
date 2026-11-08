'use client';

import { isLowConfidence, verifiedNote } from '@/lib/provenance';

/** A score number, or quiet secondary text "Unrated" when there is not enough verified data (never 0, never a dash). */
export function ScoreValue({ score, decimals = 1 }: { score: number | null | undefined; decimals?: number }) {
  if (score == null) return <span className="text-tertiary" style={{ fontWeight: 500, fontSize: '.8125rem' }} data-testid="unrated">Unrated</span>;
  return <>{score.toFixed(decimals)}</>;
}

/** Subtle 'Low confidence' tag (confidence < 0.5) with the verified-source count in the tooltip. */
export function ConfidenceTag({ confidence, signals }: { confidence?: number | null; signals?: string[] | null }) {
  if (!isLowConfidence(confidence)) return null;
  return <span className="text-tertiary t-caption" title={verifiedNote(signals) ?? undefined} data-testid="low-confidence" style={{ marginLeft: 6, fontWeight: 500 }}>Low confidence</span>;
}
