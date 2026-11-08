import {
  LayoutDashboard, Brain, TrendingUp, MapPin, BarChart3, Users, IndianRupee,
  MessageSquare, Settings, Activity, Calculator, Users2, LineChart,
  Star, CalendarDays, Radio, Sparkles, Lightbulb, DatabaseZap,
} from 'lucide-react';

export const NAV_GROUPS = [
  { title: 'Overview', items: [
    { href: '/',          icon: LayoutDashboard, label: 'Dashboard' },
    { href: '/executive', icon: BarChart3,       label: 'Executive' },
    { href: '/copilot',   icon: MessageSquare,   label: 'AI Copilot' },
  ]},
  { title: 'Discover', items: [
    { href: '/intelligence',    icon: Brain,      label: 'Intelligence' },
    { href: '/trends',          icon: TrendingUp, label: 'Trend Radar' },
    { href: '/recommendations', icon: Sparkles,   label: 'Recommendations' },
    { href: '/listening',       icon: Radio,      label: 'Social Listening' },
    { href: '/psychology',      icon: Lightbulb,  label: 'Demand Psychology' },
  ]},
  { title: 'Markets', items: [
    { href: '/markets',         icon: MapPin,       label: 'City Markets' },
    { href: '/competitors',     icon: Users,        label: 'Competitors' },
    { href: '/venues/calendar', icon: CalendarDays, label: 'Venue Calendar' },
  ]},
  { title: 'Plan & Price', items: [
    { href: '/pricing',               icon: IndianRupee, label: 'Pricing' },
    { href: '/events',                icon: Activity,    label: 'Fill-rate Monitor' },
    { href: '/events/model',          icon: Calculator,  label: 'Deal Modeler' },
    { href: '/events/pairing',        icon: Users2,      label: 'Artist Pairing' },
    { href: '/intelligence/forecast', icon: LineChart,   label: 'Demand Forecast' },
  ]},
  { title: 'Workspace', items: [
    { href: '/watchlist', icon: Star,     label: 'Watchlist' },
    { href: '/data',      icon: DatabaseZap, label: 'Data quality' },
    { href: '/settings',  icon: Settings, label: 'Settings' },
  ]},
];

export const NAV_ALL = NAV_GROUPS.flatMap(g => g.items);

export function bestMatch(pathname: string): string | undefined {
  return NAV_ALL
    .filter(i => pathname === i.href || (i.href !== '/' && pathname.startsWith(i.href)))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
}
