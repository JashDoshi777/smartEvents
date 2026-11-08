import { Fragment } from 'react';

/** Renders **bold** spans from LLM text as <strong>, and drops any other stray markdown markers. */
export function Bold({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return <>{parts.map((p, i) => (i % 2 ? <strong key={i} style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p}</strong> : <Fragment key={i}>{p.replace(/\*\*/g, '')}</Fragment>))}</>;
}
