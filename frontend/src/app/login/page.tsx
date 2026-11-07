'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/components/providers/AuthProvider';
import styles from './page.module.css';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login({ email, password });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <GlassCard className={styles.card} delay={0}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>L</div>
          <div>
            <div className="t-headline text-primary" style={{ fontWeight: 800 }}>LiveIQ</div>
            <div className="t-caption text-tertiary">by District</div>
          </div>
        </div>

        <h1 className="t-title2 text-primary" style={{ fontWeight: 800 }}>Log in</h1>
        <p className="t-footnote text-tertiary" style={{ marginTop: 4 }}>Enter your credentials to access the intelligence platform</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-email">Email</label>
            <input
              id="login-email" className="input" type="email" required
              value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com" autoComplete="email"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-password">Password</label>
            <input
              id="login-password" className="input" type="password" required
              value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password"
            />
          </div>

          {error && (
            <div className={styles.errorBox}>
              <AlertCircle size={16} color="var(--negative)" />
              <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%' }}>
            {loading ? 'Logging in...' : 'Log in'}
          </button>
        </form>

        <div className={styles.footer}>
          <span className="t-footnote text-tertiary">Don&apos;t have an account? </span>
          <Link href="/register" className="t-footnote" style={{ color: 'var(--accent)', fontWeight: 600 }}>Register</Link>
        </div>
      </GlassCard>
    </div>
  );
}
