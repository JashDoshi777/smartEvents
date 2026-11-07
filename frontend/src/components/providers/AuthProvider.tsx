'use client';

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import {
  login as apiLogin, register as apiRegister, getMe, clearTokens, getAccessToken, logoutRemote,
  AuthUser, LoginRequest, RegisterRequest,
} from '@/lib/api';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (req: LoginRequest) => Promise<void>;
  register: (req: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Routes reachable without being logged in. Everything else redirects to /login.
const PUBLIC_ROUTES = ['/login', '/register'];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      clearTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    if (loading) return;
    const isPublic = PUBLIC_ROUTES.includes(pathname);
    if (!user && !isPublic) {
      router.replace('/login');
    } else if (user && isPublic) {
      router.replace('/');
    }
  }, [loading, user, pathname, router]);

  async function login(req: LoginRequest) {
    const res = await apiLogin(req);
    setUser(res.user);
  }

  async function register(req: RegisterRequest) {
    const res = await apiRegister(req);
    setUser(res.user);
  }

  function logout() {
    // Fire-and-forget: revokes every refresh token for this user server-side
    // (see /auth/logout), but doesn't block the local logout on it resolving.
    void logoutRemote();
    clearTokens();
    setUser(null);
    router.replace('/login');
  }

  // Audit finding: children used to render unconditionally, so a hard
  // refresh on a protected route (no/expired token) briefly mounted the
  // real page — its useSWR hooks fired real requests against protected
  // endpoints before the redirect effect above had a chance to run.
  // Block rendering until the auth check resolves, and once resolved,
  // don't render protected content for a user who isn't authenticated
  // (the redirect effect will already be navigating away in that case).
  //
  // Second audit pass flagged that blocking render this way left a bare
  // blank screen with zero feedback while getMe() resolves — a real gap
  // on a slow connection, not just a security nicety. `loading` (still
  // resolving) gets a spinner; the second blockRender case (unauth user
  // on a protected route, redirect already in flight) intentionally
  // stays blank a beat rather than flashing a spinner for what's meant
  // to be an instant navigation-away.
  const isPublic = PUBLIC_ROUTES.includes(pathname);
  const blockRender = loading || (!user && !isPublic);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {loading ? (
        <div style={{
          minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'var(--bg-base)',
        }}>
          <Loader2 size={28} color="var(--text-tertiary)" className="spin" />
        </div>
      ) : blockRender ? null : children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
