'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Brain, Zap, ChevronRight } from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import styles from './page.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant';
  content: string;
  ts: Date;
  isLoading?: boolean;
}

// ── Suggested queries ─────────────────────────────────────────────────────────

const SUGGESTIONS = [
  'Which artist should we sign for Mumbai next quarter?',
  'What are the best expansion cities for EDM acts?',
  'Compare Diljit vs AP Dhillon for Delhi market',
  'Which Tier-2 cities have untapped demand?',
  'What is a fair ticket price for a 15,000 seat show?',
  'Who are the breakout artists under ₹30L guarantee?',
];

// ── Message bubble ────────────────────────────────────────────────────────────

function Bubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';
  return (
    <motion.div
      className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAssistant}`}
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {!isUser && (
        <div className={styles.aiAvatar}>
          <Brain size={14} />
        </div>
      )}
      <div className={`${styles.bubbleContent} ${isUser ? styles.bubbleContentUser : styles.bubbleContentAI}`}>
        {msg.isLoading ? (
          <div className={styles.typingDots}>
            <span /><span /><span />
          </div>
        ) : (
          <p className="t-callout" style={{ lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{msg.content}</p>
        )}
        <span className={styles.bubbleTime}>
          {msg.ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// AI Copilot Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function CopilotPage() {
  const [messages,  setMessages]  = useState<Message[]>([]);
  const [input,     setInput]     = useState('');
  const [loading,   setLoading]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || loading) return;

    const userMsg: Message = { role: 'user', content: text.trim(), ts: new Date() };
    const loadingMsg: Message = { role: 'assistant', content: '', ts: new Date(), isLoading: true };

    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setInput('');
    setLoading(true);

    try {
      const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const res = await fetch(`${BASE}/copilot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text.trim() }),
      });

      let content: string;
      if (!res.ok) {
        content = `Error ${res.status}: Could not reach the AI Copilot. Make sure the FastAPI backend is running and your Groq API key is set in backend/.env.`;
      } else {
        const data = await res.json();
        content = data.response ?? data.message ?? JSON.stringify(data);
      }

      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content, ts: new Date() };
        return next;
      });
    } catch {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = {
          role: 'assistant',
          content: 'Could not reach the AI Copilot. Make sure the FastAPI backend is running on port 8000 and your Groq API key is configured.',
          ts: new Date(),
        };
        return next;
      });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className={styles.page}>
      <Topbar title="AI Copilot" subtitle="Groq Llama 3.3 70B · District intelligence at your fingertips" />

      <div className={styles.layout}>
        {/* ── Chat area ── */}
        <div className={styles.chatPane}>
          <div className={styles.messages}>
            {messages.length === 0 ? (
              /* Welcome screen */
              <motion.div
                className={styles.welcome}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45 }}
              >
                <div className={styles.welcomeIcon}>
                  <Brain size={32} strokeWidth={1.5} />
                </div>
                <h2 className="t-title2 text-primary" style={{ marginTop: 18 }}>LiveIQ AI Copilot</h2>
                <p className="t-callout text-tertiary" style={{ maxWidth: 400, textAlign: 'center', lineHeight: 1.7, marginTop: 8 }}>
                  Ask anything about artists, cities, venues, pricing, or competitor activity. The Copilot has access to your full entity database and city intelligence.
                </p>

                <div className={styles.suggestions}>
                  {SUGGESTIONS.map((s, i) => (
                    <motion.button
                      key={s}
                      className={styles.suggestion}
                      onClick={() => send(s)}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.15 + i * 0.06, ease: [0.25, 0.46, 0.45, 0.94] }}
                    >
                      <span>{s}</span>
                      <ChevronRight size={13} color="var(--accent)" />
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            ) : (
              <div className={styles.bubbleList}>
                <AnimatePresence initial={false}>
                  {messages.map((m, i) => (
                    <Bubble key={i} msg={m} />
                  ))}
                </AnimatePresence>
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          {/* Input bar */}
          <div className={styles.inputBar}>
            <div className={styles.inputWrap}>
              <textarea
                ref={inputRef}
                className={styles.inputArea}
                placeholder="Ask about artists, cities, pricing, competitors..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                rows={1}
                disabled={loading}
              />
              <button
                className={styles.sendBtn}
                onClick={() => send(input)}
                disabled={loading || !input.trim()}
                title="Send (Enter)"
              >
                {loading
                  ? <div className={styles.sendSpinner} />
                  : <Send size={16} />
                }
              </button>
            </div>
            <p className="t-caption text-tertiary" style={{ marginTop: 8, textAlign: 'center' }}>
              Press Enter to send · Shift+Enter for new line · Powered by Groq Llama 3.3 70B
            </p>
          </div>
        </div>

        {/* ── Sidebar: context info ── */}
        <div className={styles.sidePane}>
          <div className={styles.sideSection}>
            <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.6875rem', marginBottom: 12 }}>
              What the Copilot knows
            </p>
            {[
              { icon: <Brain size={14} />, label: 'Full entity database', sub: 'All artists, films, sports & acts' },
              { icon: <Zap size={14} />, label: 'Live composite scores', sub: 'Google Trends + NewsAPI + Last.fm' },
              { icon: <Send size={14} />, label: 'City demand data', sub: 'Music market scores for 12+ cities' },
              { icon: <Brain size={14} />, label: 'Pricing benchmarks', sub: 'Historical ticket price data' },
            ].map(({ icon, label, sub }) => (
              <div key={label} className={styles.contextItem}>
                <div className={styles.contextIcon}>{icon}</div>
                <div>
                  <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{label}</p>
                  <p className="t-caption text-tertiary">{sub}</p>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.sideSection} style={{ marginTop: 20 }}>
            <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.6875rem', marginBottom: 12 }}>
              Example queries
            </p>
            {SUGGESTIONS.slice(0, 4).map(s => (
              <button
                key={s}
                className={styles.sideQuery}
                onClick={() => { setMessages([]); send(s); }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
