'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/components/providers/AuthProvider';
import styles from './page.module.css';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailErr = touched && !/^\S+@\S+\.\S+$/.test(email) ? 'Enter a valid email address' : null;
  const pwErr = touched && !password ? 'Enter your password' : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!/^\S+@\S+\.\S+$/.test(email) || !password) return;
    setLoading(true);
    try {
      await login({ email: email.trim(), password });
    } catch (err) {
      setError(typeof (err as Error)?.message === 'string' ? (err as Error).message : 'Login failed');
      setLoading(false);
    }
  }

  return (
    <main className={styles.wrap}>
      <GlassCard className={styles.card}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>L</div>
          <div>
            <h1 className="t-title1" style={{ fontWeight: 700 }}>Welcome to LiveIQ</h1>
            <p className="t-callout text-secondary" style={{ marginTop: 4 }}>Live-events intelligence for District</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-email">Email</label>
            <input id="login-email" className={`input ${styles.input} ${emailErr ? styles.invalid : ''}`} type="email" inputMode="email"
              value={email} onChange={e => setEmail(e.target.value)} placeholder="you@zomato.com" autoComplete="email" autoFocus aria-invalid={!!emailErr} />
            {emailErr && <span className={styles.fieldErr}>{emailErr}</span>}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-password">Password</label>
            <div className={styles.pwWrap}>
              <input id="login-password" className={`input ${styles.input} ${pwErr ? styles.invalid : ''}`} type={show ? 'text' : 'password'}
                value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" aria-invalid={!!pwErr} style={{ paddingRight: 46 }} />
              <button type="button" className={styles.eye} onClick={() => setShow(s => !s)} aria-label={show ? 'Hide password' : 'Show password'}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
            </div>
            {pwErr && <span className={styles.fieldErr}>{pwErr}</span>}
          </div>

          {error && (
            <div className={styles.errorBox} role="alert">
              <AlertCircle size={16} color="var(--negative)" style={{ flexShrink: 0 }} />
              <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
            </div>
          )}

          <button type="submit" className={`btn btn-primary ${styles.submit}`} disabled={loading}>
            {loading ? <><Loader2 size={16} className="spin" /> Signing in…</> : 'Sign in'}
          </button>
        </form>

        <p className={`t-footnote text-tertiary ${styles.footer}`}>
          New to LiveIQ? <Link href="/register" style={{ color: 'var(--accent)', fontWeight: 600 }}>Create an account</Link>
        </p>
      </GlassCard>
    </main>
  );
}
