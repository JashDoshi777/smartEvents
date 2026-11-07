import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/providers/ThemeProvider';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { AppShell } from '@/components/layout/AppShell';
import { SWRProvider } from '@/lib/swr';
import { MarketScopeProvider } from '@/components/providers/MarketScopeProvider';
import { ToastProvider } from '@/components/ui/Toast';

// Self-hosted via next/font — no runtime request to Google, no flash of
// unstyled text. This is the FALLBACK face: real Apple devices render
// actual SF Pro for free via the `-apple-system` stack ahead of it in
// --font-sans (globals.css); Inter only shows on non-Apple systems.
const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'LiveIQ — District Intelligence',
  description: 'Real-time intelligence for District by Zomato — artist scoring, city demand, venue selection, and pricing optimization.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      {/*
        No data-theme attribute here — an explicit stamp would force one
        theme before ThemeProvider's inline script runs. The inline
        script below sets data-theme synchronously (before paint, before
        hydration) from localStorage or prefers-color-scheme, so there's
        no flash of the wrong theme.
      */}
      <head>
        <script
          // Runs before paint — reads a saved preference or falls back to
          // the OS theme, so a system-dark visitor never sees a light
          // flash (or vice versa) before React hydrates.
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('liveiq-theme');if(!t){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`,
          }}
        />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <SWRProvider>
              <MarketScopeProvider>
                <ToastProvider>
                  <AppShell>{children}</AppShell>
                </ToastProvider>
              </MarketScopeProvider>
            </SWRProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
