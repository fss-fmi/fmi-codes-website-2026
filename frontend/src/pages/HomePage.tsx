import Navbar from '@/components/layout/Navbar';
import HeroSection from '@/components/home/HeroSection';
import BentoGrid from '@/components/home/BentoGrid';
import SponsorsSection from '@/components/home/SponsorsSection';
import ContactSection from '@/components/home/ContactSection';
import { useScrollReveal } from '@/hooks/useVisuals';

export default function HomePage() {
  useScrollReveal();

  return (
    <>
      <Navbar />
      <main>
        <HeroSection />
        <BentoGrid />
        <SponsorsSection />
        <ContactSection />
      </main>
    </>
  );
}
