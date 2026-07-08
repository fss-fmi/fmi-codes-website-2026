import Navbar from '@/components/layout/Navbar';
import MentorsStayTunedPage from './MentorsStayTunedPage';
import { useConfig } from '@/context/ConfigContext';
import VariantBCompanyLog from './variants/VariantBCompanyLog';

export default function MentorsPage() {
  const { MENTORS_STAY_TUNED } = useConfig();

  return (
    <>
      <Navbar />
      {MENTORS_STAY_TUNED ? <MentorsStayTunedPage /> : <VariantBCompanyLog />}
    </>
  );
}
