/**
 * Canonical sponsor data shared by the desktop SponsorsSection and the
 * MobileHomePage. Both consumers use the same {file, alt} shape; mobile
 * maps to just the `alt` string where it only needs the name.
 *
 * Scale overrides and contact channels stay local to their consumers —
 * they carry layout-specific values (the desktop marquee needs finer
 * per-logo scaling than the mobile grid) and are not shared data.
 */

export interface Sponsor {
  file: string;
  alt: string;
}

export const PREMIUM_SPONSORS: readonly Sponsor[] = [
  { file: 'avenga.svg', alt: 'Avenga' },
  { file: 'gameloft.png', alt: 'Gameloft' },
  { file: 'EnduroSat.png', alt: 'EnduroSat' },
  { file: 'waracle.png', alt: 'Waracle' },
  { file: 'SAP.png', alt: 'SAP' },
  { file: 'Milestone.png', alt: 'Milestone' },
] as const;

export const SUPPORTING_SPONSORS: readonly Sponsor[] = [
  { file: 'astea.svg', alt: 'Astea' },
  { file: 'chaos.jpg', alt: 'Chaos' },
  { file: 'Dreamix.png', alt: 'Dreamix' },
  { file: 'engineerAcces.png', alt: 'Engineer Access' },
  { file: 'raven.svg', alt: 'Raven' },
  { file: 'Experian.jpg', alt: 'Experian' },
] as const;
