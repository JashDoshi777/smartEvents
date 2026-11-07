'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';

const EXPANDED_WIDTH = 240;
const COLLAPSED_WIDTH = 72;

// Auth pages render full-bleed with no sidebar/topbar chrome — there's
// nothing to navigate to until the user is logged in.
const CHROMELESS_ROUTES = ['/login', '/register'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  if (CHROMELESS_ROUTES.includes(pathname)) {
    return <main id="main-content" style={{ marginLeft: 0, paddingTop: 0 }}>{children}</main>;
  }

  return (
    <>
      <Sidebar collapsed={collapsed} onCollapsedChange={setCollapsed} />
      <main
        id="main-content"
        style={{ marginLeft: collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH }}
      >
        {children}
      </main>
    </>
  );
}
