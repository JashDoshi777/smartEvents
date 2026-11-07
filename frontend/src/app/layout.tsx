import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/providers/ThemeProvider';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { AppShell } from '@/components/layout/AppShell';

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
  title: 'LiveIQ — District Intelligence Platform',
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
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </ThemeProvider>
        <style>{`
          #main-content {
            min-height: 100vh;
            padding-top: 60px;
            transition: margin-left 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
          }
        `}</style>
      </body>
    </html>
  );
}
