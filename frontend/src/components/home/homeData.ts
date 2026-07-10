/**
 * Canonical home content shared across the desktop sections, the
 * MobileHomePage, and the PartnersPage:
 *
 * - Sponsor {file, alt, scale} data. Consumers read `scale ?? 1`; PartnersPage
 *   additionally multiplies the shared scale by its own 0.9 tile factor.
 * - Contact channels ({label, value, href, external}) shared by the desktop
 *   ContactSection and the MobileHomePage.
 *
 * Each consumer keeps its own rendering/layout — only the underlying data
 * lives here.
 */

export interface Sponsor {
  file: string;
  alt: string;
  scale?: number;
}

export const PREMIUM_SPONSORS: readonly Sponsor[] = [
  { file: 'avenga.svg', alt: 'Avenga' },
  { file: 'gameloft.png', alt: 'Gameloft' },
  { file: 'EnduroSat.png', alt: 'EnduroSat' },
  { file: 'waracle.png', alt: 'Waracle', scale: 1.2 },
  { file: 'SAP.png', alt: 'SAP' },
  { file: 'Milestone.png', alt: 'Milestone', scale: 1.5 },
] as const;

export const SUPPORTING_SPONSORS: readonly Sponsor[] = [
  { file: 'astea.svg', alt: 'Astea', scale: 1.2 },
  { file: 'chaos.jpg', alt: 'Chaos' },
  { file: 'Dreamix.png', alt: 'Dreamix', scale: 1.4 },
  { file: 'engineerAcces.png', alt: 'Engineer Access', scale: 1.15 },
  { file: 'raven.svg', alt: 'Raven', scale: 1.25 },
  { file: 'Experian.jpg', alt: 'Experian', scale: 1.2 },
] as const;

export interface ContactChannel {
  label: string;
  value: string;
  href: string;
  external: boolean;
}

export const CONTACT_CHANNELS: readonly ContactChannel[] = [
  {
    label: 'INSTAGRAM',
    value: '@fmicodes',
    href: 'https://www.instagram.com/fmicodes/',
    external: true,
  },
  {
    label: 'FACEBOOK',
    value: 'fmicodes',
    href: 'https://www.facebook.com/fmicodes',
    external: true,
  },
  {
    label: 'EMAIL',
    value: 'fss@fmi.uni-sofia.bg',
    href: 'mailto:fss@fmi.uni-sofia.bg',
    external: false,
  },
  {
    label: 'PHONE',
    value: '+359 888 888 888',
    href: 'tel:+359888888888',
    external: false,
  },
] as const;
