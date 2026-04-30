import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import MentorSelectionGrid from '@/components/mentors/MentorSelectionGrid';
import MentorsStayTunedPage from './MentorsStayTunedPage';
import { useConfig } from '@/context/ConfigContext';
import api from '@/lib/api';
import type { Mentor } from '@/types/mentor';

export default function MentorsPage() {
  const { MENTORS_STAY_TUNED } = useConfig();

  const { data, isLoading } = useQuery<{ success: boolean; mentors: Mentor[] }>({
    queryKey: ['mentors'],
    queryFn: () => api.get('/api/mentors'),
    staleTime: 5 * 60_000,
    enabled: !MENTORS_STAY_TUNED,
  });

  const mentors = data?.mentors ?? [];

  return (
    <>
      <Navbar />
      {MENTORS_STAY_TUNED ? (
        <MentorsStayTunedPage />
      ) : (
        <MentorSelectionGrid
          mentors={mentors}
          isLoading={isLoading}
        />
      )}
    </>
  );
}
