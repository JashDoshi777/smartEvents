'use client';

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp, Check, ChevronDown, ChevronRight, RotateCcw, Sparkles, Square, SquarePen } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { getAccessToken, getCopilotModels } from '@/lib/api';
import styles from './page.module.css';

interface Msg { id: number; role: 'user' | 'assistant'; content: string; ts: number; error?: string; streaming?: boolean }

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const SUGGESTIONS = [
  'Which Tier-2 city should District expand to next?',
  'Which Indian artists are breaking out right now?',
  'What is a fair ticket price for a 5,000-seat Bengaluru indie show?',
  'Compare Mumbai and Delhi NCR for live comedy demand',
  'How should we plan around monsoon season for outdoor events?',
  'Which acts could headline an IPL-week concert in Hyderabad?',
];

/* ── markdown-lite (safe: builds React nodes, never raw HTML) ── */
function inline(text: string, key: string) {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith('**')) out.push(<strong key={`${key}b${i}`}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith('`')) out.push(<code key={`${key}c${i}`}>{t.slice(1, -1)}</code>);
    else out.push(<em key={`${key}e${i}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length; i++;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const res: React.ReactNode[] = [];
    const lines = text.replace(/[ \t]+\n/g, '\n').split('\n');
    let i = 0, k = 0;
    while (i < lines.length) {
      const l = lines[i];
      if (/^```/.test(l)) {
        const buf: string[] = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        i++; res.push(<pre key={k++}>{buf.join('\n')}</pre>); continue;
      }
      if (/^\s*[-*•]\s+/.test(l)) {
        const items: string[] = [];
        while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*•]\s+/, ''));
        res.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `u${k}${j}`)}</li>)}</ul>); continue;
      }
      if (/^\s*\d+[.)]\s+/.test(l)) {
        const items: string[] = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ''));
        res.push(<ol key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `o${k}${j}`)}</li>)}</ol>); continue;
      }
      if (/^#{1,4}\s+/.test(l)) { res.push(<h4 key={k++}>{inline(l.replace(/^#{1,4}\s+/, ''), `h${k}`)}</h4>); i++; continue; }
      if (!l.trim()) { i++; continue; }
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(```|\s*[-*•]\s+|\s*\d+[.)]\s+|#{1,4}\s+)/.test(lines[i])) buf.push(lines[i++]);
      res.push(<p key={k++}>{buf.map((t, j) => <Fragment key={j}>{j > 0 && <br />}{inline(t, `p${k}${j}`)}</Fragment>)}</p>);
    }
    return res;
  }, [text]);
  return <div className={styles.md}>{blocks}</div>;
}

const time = (t: number) => new Date(t).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });

export default function CopilotPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState('');
  const [menu, setMenu] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const { data: models } = useSWR('copilot/models', getCopilotModels, { shouldRetryOnError: false });
  const active = models?.available_models.find(m => m.id === (model || models.current_model));

  useEffect(() => {
    if (!menu) return;
    const close = (e: PointerEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [menu]);

  // auto-scroll while the user is at the bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [msgs]);
  const onScroll = () => {
    const el = scrollRef.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: number, p: Partial<Msg> | ((m: Msg) => Partial<Msg>)) =>
    setMsgs(list => list.map(m => m.id === id ? { ...m, ...(typeof p === 'function' ? p(m) : p) } : m)), []);

  const run = useCallback(async (history: Msg[]) => {
    const aid = ++idRef.current;
    setMsgs([...history, { id: aid, role: 'assistant', content: '', ts: Date.now(), streaming: true }]);
    stick.current = true;
    setBusy(true);
    const ac = new AbortController();
    abortRef.current = ac;
    const payload = {
      messages: history.filter(m => !m.error).slice(-12).map(m => ({ role: m.role, content: m.content.slice(0, 7900) })),
      model: model || undefined, max_tokens: 1024,
    };
    const headers = { 'Content-Type': 'application/json', ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}) };
    let got = '';
    const fail = (msg: string) => patch(aid, { streaming: false, error: msg });
    try {
      let streamErr: string | null = null;
      const res = await fetch(`${BASE}/copilot/stream`, { method: 'POST', headers, body: JSON.stringify(payload), signal: ac.signal });
      if (res.status === 401) throw new Error('Your session expired. Please sign in again.');
      if (res.status === 503) throw new Error('The AI Copilot isn’t configured on this server yet.');
      if (!res.ok || !res.body) streamErr = `stream ${res.status}`;
      else {
        const reader = res.body.getReader(), dec = new TextDecoder();
        let buf = '', done = false;
        while (!done) {
          const { value, done: d } = await reader.read();
          if (d) break;
          buf += dec.decode(value, { stream: true });
          const parts = buf.split('\n\n'); buf = parts.pop() ?? '';
          for (const part of parts) {
            const line = part.split('\n').find(l => l.startsWith('data:'));
            if (!line) continue;
            const data = line.slice(5).trim();
            if (data === '[DONE]') { done = true; break; }
            try {
              const j = JSON.parse(data);
              if (j.error) { streamErr = String(j.error); done = true; break; }
              if (j.chunk) { got += j.chunk; const snap = got; patch(aid, { content: snap }); }
            } catch { /* partial frame */ }
          }
        }
      }
      if (streamErr && !got) {
        // streaming unavailable: fall back to the single-shot endpoint and reveal it progressively
        const r = await fetch(`${BASE}/copilot/chat`, { method: 'POST', headers, body: JSON.stringify(payload), signal: ac.signal });
        if (!r.ok) throw new Error(r.status === 503 ? 'The AI Copilot isn’t configured on this server yet.' : 'The AI service is not responding right now. Please try again in a moment.');
        const { response } = await r.json() as { response: string };
        for (let i = 0; i < response.length; i += 6) {
          if (ac.signal.aborted) break;
          patch(aid, { content: response.slice(0, i + 6) });
          await new Promise(r2 => setTimeout(r2, 12));
        }
        got = response;
      } else if (streamErr && got) {
        patch(aid, { streaming: false, error: 'The response was interrupted.' }); return;
      }
      patch(aid, { streaming: false, content: got });
    } catch (e) {
      if (ac.signal.aborted) { patch(aid, m => ({ streaming: false, content: m.content || '', error: m.content ? undefined : 'Stopped.' })); return; }
      fail(e instanceof Error && !/fetch|network|Failed/i.test(e.message) ? e.message : 'Couldn’t reach the server. Check your connection and try again.');
    } finally { setBusy(false); abortRef.current = null; }
  }, [model, patch]);

  const send = useCallback((text: string) => {
    const t = text.trim().slice(0, 4000);
    if (!t || busy) return;
    setInput('');
    if (taRef.current) taRef.current.style.height = 'auto';
    run([...msgs.filter(m => !(m.error && !m.content)), { id: ++idRef.current, role: 'user', content: t, ts: Date.now() }]);
  }, [busy, msgs, run]);

  const retry = () => {
    const lastUser = [...msgs].reverse().find(m => m.role === 'user');
    if (!lastUser) return;
    const idx = msgs.findIndex(m => m.id === lastUser.id);
    run(msgs.slice(0, idx + 1));
  };
  const newChat = () => { abortRef.current?.abort(); setMsgs([]); setBusy(false); setInput(''); };

  return (
    <Page title="AI Copilot" subtitle="Ask about artists, cities and pricing" fill>
      <div className={styles.root}>
        <div className={styles.toolbar}>
          <div className={styles.menuWrap} ref={menuRef}>
            <button type="button" className={styles.modelBtn} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(o => !o)} disabled={!models}>
              <span>{active?.name ?? 'Model'}</span><ChevronDown size={14} />
            </button>
            <AnimatePresence>
              {menu && models && (
                <motion.div className={styles.menu} role="menu" initial={{ opacity: 0, y: -6, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: .18 }}>
                  {models.available_models.map(m => (
                    <button key={m.id} type="button" role="menuitemradio" aria-checked={active?.id === m.id} className={styles.menuItem} onClick={() => { setModel(m.id); setMenu(false); }}>
                      <div style={{ flex: 1 }}><b style={{ fontSize: '.875rem' }}>{m.name}</b><small>{m.description}</small></div>
                      {active?.id === m.id && <Check size={16} color="var(--accent)" />}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <button type="button" className={styles.newChat} onClick={newChat} disabled={msgs.length === 0} aria-label="New chat"><SquarePen size={16} strokeWidth={1.7} /> New chat</button>
        </div>

        <div className={styles.scroll} ref={scrollRef} onScroll={onScroll}>
          {msgs.length === 0 ? (
            <motion.div className={styles.welcome} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', stiffness: 200, damping: 24 }}>
              <h2 className={styles.wTitle}>Ask about the Indian live-events market</h2>
              <p className={styles.wSub}>Artists, cities, pricing and timing, answered with LiveIQ’s context.</p>
              {models && !models.groq_configured && <p className="t-footnote" style={{ color: 'var(--warning)' }}>The AI provider isn’t configured on this server, so answers may fail.</p>}
              <div className={styles.sugg}>
                {SUGGESTIONS.map(sg => <button key={sg} type="button" className={styles.suggBtn} onClick={() => send(sg)}><span>{sg}</span><ChevronRight size={16} /></button>)}
              </div>
            </motion.div>
          ) : (
            <div className={styles.thread} role="log" aria-live="polite">
              <div className={styles.stamp}>Today {time(msgs[0].ts)}</div>
              {msgs.map((m, idx) => {
                const user = m.role === 'user';
                const lastOfRun = msgs[idx + 1]?.role !== m.role;
                const firstOfRun = msgs[idx - 1]?.role !== m.role;
                return (
                  <motion.div key={m.id} style={{ marginTop: firstOfRun && idx ? 8 : 0 }} initial={{ opacity: 0, y: 10, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: .28, ease: [0.22, 1, 0.36, 1] }}>
                    <div className={`${styles.row} ${user ? styles.rowUser : ''}`}>
                      <div data-role={user ? "user" : "assistant"} className={`${styles.bubble} ${user ? styles.user : styles.ai} ${lastOfRun ? styles.tail : ''} ${m.error && !m.content ? styles.errBubble : ''}`}>
                        {user ? m.content : (
                          <>
                            {m.streaming && !m.content ? <span className={styles.dots} aria-label="Copilot is typing"><i /><i /><i /></span> : m.content ? <Markdown text={m.content} /> : null}
                            {m.streaming && m.content && <span className={styles.cursor} />}
                            {m.error && (
                              <div role="alert" style={{ color: 'var(--negative)', fontSize: '.875rem' }}>
                                {m.error}
                                {m.error !== 'Stopped.' && <div><button type="button" className={`btn btn-tinted btn-sm ${styles.retry}`} onClick={retry}><RotateCcw size={13} /> Try again</button></div>}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>

        <div className={styles.composer}>
          <form className={styles.composerIn} onSubmit={e => { e.preventDefault(); send(input); }}>
            <textarea ref={taRef} rows={1} value={input} placeholder="Ask LiveIQ Copilot" aria-label="Message" enterKeyHint="send"
              onChange={e => { setInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`; }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }} />
            {busy
              ? <button type="button" className={`${styles.send} ${styles.stop}`} aria-label="Stop generating" onClick={() => abortRef.current?.abort()}><Square size={13} fill="currentColor" /></button>
              : <button type="submit" className={styles.send} aria-label="Send" disabled={!input.trim()}><ArrowUp size={18} strokeWidth={2.6} /></button>}
          </form>
          <p className={styles.foot}>AI can make mistakes. Verify numbers before booking decisions.</p>
        </div>
      </div>
    </Page>
  );
}
