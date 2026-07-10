import { useConfig } from '@/context/ConfigContext';
import RankingsTBDPage from './RankingsTBDPage';
import RankingsLivePage from './RankingsLivePage';

export default function RankingsPage() {
  const { RANKINGS_LIVE } = useConfig();
  return RANKINGS_LIVE ? <RankingsLivePage /> : <RankingsTBDPage />;
}
