'use client';

import { createContext, useCallback, useContext, useRef, useState } from 'react';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';

type Kind = 'success' | 'error' | 'info';
interface ToastItem { id: number; kind: Kind; message: string }

const Ctx = createContext<(message: string, kind?: Kind) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((message: string, kind: Kind = 'info') => {
    const id = ++seq.current;
    setItems(list => [...list.slice(-2), { id, kind, message }]);
    setTimeout(() => setItems(list => list.filter(t => t.id !== id)), 3600);
  }, []);

  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {items.map(t => {
          const Icon = t.kind === 'success' ? CheckCircle2 : t.kind === 'error' ? AlertCircle : Info;
          const color = t.kind === 'success' ? 'var(--positive)' : t.kind === 'error' ? 'var(--negative)' : 'var(--accent)';
          return (
            <div key={t.id} className="toast"><Icon size={18} color={color} />{t.message}</div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

/** `const toast = useToast(); toast('Saved', 'success')` */
export const useToast = () => useContext(Ctx);
