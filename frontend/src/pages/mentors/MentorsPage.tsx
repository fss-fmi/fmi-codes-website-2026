import Navbar from '@/components/layout/Navbar';
import MentorSelectionGrid from '@/components/mentors/MentorSelectionGrid';
import MentorsStayTunedPage from './MentorsStayTunedPage';
import { useConfig } from '@/context/ConfigContext';

export default function MentorsPage() {
  const { MENTORS_STAY_TUNED } = useConfig();

  return (
    <>
      <Navbar />
      {MENTORS_STAY_TUNED ? <MentorsStayTunedPage /> : <MentorSelectionGrid />}
    </>
  );
}
