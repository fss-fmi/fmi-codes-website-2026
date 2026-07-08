import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import queryClient from '@/lib/queryClient';
import { AuthProvider } from '@/context/AuthContext';
import { ConfigProvider } from '@/context/ConfigContext';
import RouteErrorBoundary from '@/components/common/ErrorBoundary';
import { ToastProvider } from '@/components/common/useToast';

import HomePage from '@/pages/HomePage';
import RegulationsPage from '@/pages/RegulationsPage';
import SchedulePage from '@/pages/SchedulePage';
import PartnersPage from '@/pages/PartnersPage';
import NotFoundPage from '@/pages/NotFoundPage';

import LoginPage from '@/pages/auth/LoginPage';
import RegistrationPage from '@/pages/auth/RegistrationPage';
import RegistrationClosedPage from '@/pages/auth/RegistrationClosedPage';
import ProfilePage from '@/pages/auth/ProfilePage';
import ResetPasswordPage from '@/pages/auth/ResetPasswordPage';

import MentorsPage from '@/pages/mentors/MentorsPage';
import ChooseMentorPage from '@/pages/mentors/ChooseMentorPage';
import MentorDashboardPage from '@/pages/mentors/MentorDashboardPage';
import SelectedMentorsPage from '@/pages/mentors/SelectedMentorsPage';

import TeamPage from '@/pages/teams/TeamPage';
import CreateTeamPage from '@/pages/teams/CreateTeamPage';
import JoinTeamPage from '@/pages/teams/JoinTeamPage';
import BrowseTeamsPage from '@/pages/teams/BrowseTeamsPage';
import RegisteredTeamsPage from '@/pages/teams/RegisteredTeamsPage';

import RankingsPage from '@/pages/rankings/RankingsPage';
import RankingsLivePage from '@/pages/rankings/RankingsLivePage';

import MatchingPage from '@/pages/admin/MatchingPage';
import { useConfig } from '@/context/ConfigContext';

function RegistrationGate() {
  const { REGISTRATION_OPEN } = useConfig();
  return REGISTRATION_OPEN ? <RegistrationPage /> : <RegistrationClosedPage />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ConfigProvider>
          <ToastProvider>
            <BrowserRouter>
              <RouteErrorBoundary>
              <Routes>
                {/* Public */}
                <Route
                  path="/"
                  element={<HomePage />}
                />
                <Route
                  path="/regulations"
                  element={<RegulationsPage />}
                />
                <Route
                  path="/schedule"
                  element={<SchedulePage />}
                />
                <Route
                  path="/partners"
                  element={<PartnersPage />}
                />
                <Route
                  path="/mentors"
                  element={<MentorsPage />}
                />
                <Route
                  path="/registeredTeams"
                  element={<RegisteredTeamsPage />}
                />
                <Route
                  path="/rankings"
                  element={<RankingsPage />}
                />
                <Route
                  path="/rankings/live"
                  element={<RankingsLivePage />}
                />

                {/* Auth */}
                <Route
                  path="/login"
                  element={<LoginPage />}
                />
                <Route
                  path="/reset-password"
                  element={<ResetPasswordPage />}
                />
                <Route
                  path="/registration"
                  element={<RegistrationGate />}
                />
                <Route
                  path="/profile"
                  element={<ProfilePage />}
                />

                {/* Participant */}
                <Route
                  path="/team"
                  element={<TeamPage />}
                />
                <Route
                  path="/createTeam"
                  element={<CreateTeamPage />}
                />
                <Route
                  path="/joinTeam"
                  element={<JoinTeamPage />}
                />
                <Route
                  path="/browseTeams"
                  element={<BrowseTeamsPage />}
                />
                <Route
                  path="/chooseMentor"
                  element={<ChooseMentorPage />}
                />
                <Route
                  path="/selectedMentors"
                  element={<SelectedMentorsPage />}
                />

                {/* Mentor */}
                <Route
                  path="/mentorDashboard"
                  element={<MentorDashboardPage />}
                />

                {/* Admin */}
                <Route
                  path="/admin/matching"
                  element={<MatchingPage />}
                />

                {/* Fallback */}
                <Route
                  path="*"
                  element={<NotFoundPage />}
                />
              </Routes>
            </RouteErrorBoundary>
          </BrowserRouter>
          </ToastProvider>
        </ConfigProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
