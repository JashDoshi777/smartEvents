import type { CSSProperties } from 'react';

export function Skeleton({ width = '100%', height = 14, radius, style, className = '' }: {
  width?: number | string; height?: number | string; radius?: number | string; style?: CSSProperties; className?: string;
}) {
  return <div className={`skeleton ${className}`} style={{ width, height, borderRadius: radius, ...style }} aria-hidden />;
}

/** A card-shaped placeholder with title + n lines. */
export function SkeletonCard({ lines = 3, height }: { lines?: number; height?: number }) {
  return (
    <div className="glass-card" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, minHeight: height }} aria-busy="true" aria-label="Loading">
      <Skeleton width="38%" height={18} />
      {Array.from({ length: lines }).map((_, i) => <Skeleton key={i} width={`${92 - i * 11}%`} height={12} />)}
    </div>
  );
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} height={52} radius={14} />)}
    </div>
  );
}
