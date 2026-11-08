import Link from 'next/link';
import { Compass } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { EmptyState } from '@/components/ui/States';

export default function NotFound() {
  return (
    <Page title="Page not found" subtitle="That address doesn’t exist in LiveIQ">
      <GlassCard>
        <EmptyState icon={<Compass size={34} strokeWidth={1.4} />} title="We couldn’t find that page" message="The link may be old or mistyped."
          action={<Link href="/" className="btn btn-primary">Back to dashboard</Link>} />
      </GlassCard>
    </Page>
  );
}
