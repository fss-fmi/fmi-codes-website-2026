import type { ReactNode } from 'react';
import SectionHeader from '@/components/common/SectionHeader';

/**
 * Header row shared by all Regulations variants. Thin wrapper over the shared
 * SectionHeader — kept for the existing import path. Exposes the h1 via
 * headingId for aria-labelledby / anchor targeting.
 */
export default function RegulationsHeader({
  title,
  caption,
  right,
}: {
  title: string;
  caption: string;
  right?: ReactNode;
}) {
  return (
    <SectionHeader
      title={title}
      caption={caption}
      right={right}
      headingId="regulations-heading"
    />
  );
}
