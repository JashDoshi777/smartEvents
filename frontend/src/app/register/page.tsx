'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/components/providers/AuthProvider';
import styles from './page.module.css';

export default function RegisterPage() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameErr = touched && !fullName.trim() ? 'Enter your name' : null;
  const emailErr = touched && !/^\S+@\S+\.\S+$/.test(email) ? 'Enter a valid email address' : null;
  const pwErr = (touched || password.length > 0) && password.length < 8 ? 'Use at least 8 characters' : null;
  const valid = fullName.trim() && /^\S+@\S+\.\S+$/.test(email) && password.length >= 8;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!valid) return;
    setLoading(true);
    try {
      await register({ email: email.trim(), password, full_name: fullName.trim() });
    } catch (err) {
      setError(typeof (err as Error)?.message === 'string' && !(err as Error).message.startsWith('[') ? (err as Error).message : 'Registration failed. Check your details and try again.');
      setLoading(false);
    }
  }

  return (
    <main className={styles.wrap}>
      <GlassCard className={styles.card}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>L</div>
          <div>
            <h1 className="t-title1" style={{ fontWeight: 700 }}>Create your account</h1>
            <p className="t-callout text-secondary" style={{ marginTop: 4 }}>Start exploring live-events intelligence</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-name">Full name</label>
            <input id="reg-name" className={`input ${styles.input} ${nameErr ? styles.invalid : ''}`} value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Aarav Sharma" autoComplete="name" autoFocus aria-invalid={!!nameErr} />
            {nameErr && <span className={styles.fieldErr}>{nameErr}</span>}
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-email">Email</label>
            <input id="reg-email" className={`input ${styles.input} ${emailErr ? styles.invalid : ''}`} type="email" inputMode="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@zomato.com" autoComplete="email" aria-invalid={!!emailErr} />
            {emailErr && <span className={styles.fieldErr}>{emailErr}</span>}
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="reg-password">Password</label>
            <div className={styles.pwWrap}>
              <input id="reg-password" className={`input ${styles.input} ${pwErr ? styles.invalid : ''}`} type={show ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" autoComplete="new-password" aria-invalid={!!pwErr} style={{ paddingRight: 46 }} />
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
            {loading ? <><Loader2 size={16} className="spin" /> Creating account…</> : 'Create account'}
          </button>
        </form>

        <p className={`t-footnote text-tertiary ${styles.footer}`}>
          Already have an account? <Link href="/login" style={{ color: 'var(--accent)', fontWeight: 600 }}>Sign in</Link>
        </p>
      </GlassCard>
    </main>
  );
}
