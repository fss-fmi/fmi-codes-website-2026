import type { ReactNode } from 'react';
import SectionHeader from '@/components/common/SectionHeader';

/**
 * Header row shared by all Mentors variants. Thin wrapper over the shared
 * SectionHeader — kept for the existing import path.
 */
export default function MentorsHeader({
  title,
  caption,
  right,
}: {
  title: string;
  caption: string;
  right?: ReactNode;
}) {
  return <SectionHeader title={title} caption={caption} right={right} />;
}
