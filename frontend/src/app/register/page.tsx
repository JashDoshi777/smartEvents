'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/components/providers/AuthProvider';
import styles from './page.module.css';

export default function RegisterPage() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      // No role field — every self-registered account starts as a
      // read-only viewer; elevation is an admin action, not self-service.
      await register({ email, password, full_name: fullName });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
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

        <h1 className="t-title2 text-primary" style={{ fontWeight: 800 }}>Create an account</h1>
        <p className="t-footnote text-tertiary" style={{ marginTop: 4 }}>Get access to the intelligence platform</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-name">Full name</label>
            <input
              id="reg-name" className="input" type="text" required
              value={fullName} onChange={e => setFullName(e.target.value)}
              placeholder="Jane Doe" autoComplete="name"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-email">Email</label>
            <input
              id="reg-email" className="input" type="email" required
              value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com" autoComplete="email"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-password">Password</label>
            <input
              id="reg-password" className="input" type="password" required minLength={8}
              value={password} onChange={e => setPassword(e.target.value)}
              placeholder="At least 8 characters" autoComplete="new-password"
            />
          </div>

          {error && (
            <div className={styles.errorBox}>
              <AlertCircle size={16} color="var(--negative)" />
              <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%' }}>
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <div className={styles.footer}>
          <span className="t-footnote text-tertiary">Already have an account? </span>
          <Link href="/login" className="t-footnote" style={{ color: 'var(--accent)', fontWeight: 600 }}>Log in</Link>
        </div>
      </GlassCard>
    </div>
  );
}
