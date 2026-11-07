'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';
import { ShellContext } from './shell-context';

const CHROMELESS_ROUTES = ['/login', '/register'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    try { if (localStorage.getItem('liveiq-sidebar') === '1') setCollapsed(true); } catch { /* ignore */ }
  }, []);
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const setCollapsedPersist = (v: boolean) => {
    setCollapsed(v);
    try { localStorage.setItem('liveiq-sidebar', v ? '1' : '0'); } catch { /* ignore */ }
  };

  if (CHROMELESS_ROUTES.includes(pathname)) {
    return <main id="main-content" style={{ marginLeft: 0 }}>{children}</main>;
  }

  return (
    <ShellContext.Provider value={{ openMenu: () => setMobileOpen(true) }}>
      <Sidebar collapsed={collapsed} onCollapsedChange={setCollapsedPersist} mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
      <main id="main-content" style={{ marginLeft: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)' }}>
        {children}
      </main>
    </ShellContext.Provider>
  );
}
