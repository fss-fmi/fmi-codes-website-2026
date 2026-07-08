import Navbar from '@/components/layout/Navbar';
import HeroSection from '@/components/home/HeroSection';
import BriefingSection from '@/components/home/BriefingSection';
import SponsorsSection from '@/components/home/SponsorsSection';
import ContactSection from '@/components/home/ContactSection';
import { useScrollReveal } from '@/hooks/useVisuals';

export default function HomePage() {
  useScrollReveal();

  return (
    <>
      <Navbar />
      <main>
        <section
          style={{
            background: 'var(--px-bg)',
            display: 'flex',
            justifyContent: 'center',
            padding: '32px 24px 0',
            marginBottom: '-32px',
            position: 'relative',
            zIndex: 1,
          }}
        >
          <img
            src="/images/codes_logo2.svg"
            alt="FMI Codes 2026"
            style={{
              display: 'block',
              width: '100%',
              maxWidth: 'min(440px, 60vw)',
              height: 'auto',
            }}
          />
        </section>
        <HeroSection />
        <BriefingSection />
        <SponsorsSection />
        <ContactSection />
      </main>
    </>
  );
}
