import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MentorsPanel from './MentorsPanel';

const prefs = [{ mentor_id: 4, rank: 1, mentor_name: 'Ana Petrova' }];

function renderPanel(props: {
  isRegistered: boolean;
  isCaptain?: boolean;
  withPrefs?: boolean;
  preferencesOpen?: boolean;
  confirmed?: boolean | undefined;
}) {
  render(
    <MemoryRouter>
      <MentorsPanel
        confirmed={'confirmed' in props ? props.confirmed : false}
        mentors={[]}
        prefs={props.withPrefs ? prefs : []}
        isCaptain={props.isCaptain ?? true}
        isRegistered={props.isRegistered}
        preferencesOpen={props.preferencesOpen ?? true}
      />
    </MemoryRouter>,
  );
}

test('captain of a registered team gets CHOOSE MENTORS', () => {
  renderPanel({ isRegistered: true });
  expect(screen.getByText('CHOOSE MENTORS')).toBeInTheDocument();
});

test.each([true, false])('team that is not registered gets no CTA (captain: %s)', (isCaptain) => {
  renderPanel({ isRegistered: false, isCaptain });
  expect(screen.queryByText('CHOOSE MENTORS')).toBeNull();
  expect(
    screen.getByText(/only registered teams take part in mentor matching/i),
  ).toBeInTheDocument();
});

test('a ranking left over from before the team lost its slot is not shown as waiting', () => {
  renderPanel({ isRegistered: false, withPrefs: true });
  expect(screen.queryByText(/waiting for matching/i)).toBeNull();
  expect(screen.queryByText('Ana Petrova')).toBeNull();
});

test.each([true, false])(
  'while submissions are closed there is no CTA, only the note (captain: %s)',
  (isCaptain) => {
    renderPanel({ isRegistered: true, isCaptain, preferencesOpen: false });
    expect(screen.queryByText('CHOOSE MENTORS')).toBeNull();
    expect(screen.queryByText(/waiting for the captain/i)).toBeNull();
    expect(screen.getByText(/preference submission is closed/i)).toBeInTheDocument();
  },
);

test('a submitted ranking still shows while submissions are closed', () => {
  renderPanel({ isRegistered: true, withPrefs: true, preferencesOpen: false });
  expect(screen.getByText('Ana Petrova')).toBeInTheDocument();
  expect(screen.getByText(/waiting for matching/i)).toBeInTheDocument();
  expect(screen.queryByText('UPDATE PREFERENCES')).toBeNull();
});

test('the captain can go back and update a submitted ranking while submissions are open', () => {
  renderPanel({ isRegistered: true, withPrefs: true });
  expect(screen.getByText('UPDATE PREFERENCES').closest('a')).toHaveAttribute(
    'href',
    '/chooseMentor',
  );
});

test('a member who is not captain gets no update link', () => {
  renderPanel({ isRegistered: true, withPrefs: true, isCaptain: false });
  expect(screen.getByText(/waiting for matching/i)).toBeInTheDocument();
  expect(screen.queryByText('UPDATE PREFERENCES')).toBeNull();
});

test('no update link until the matching status has loaded', () => {
  renderPanel({ isRegistered: true, withPrefs: true, confirmed: undefined });
  expect(screen.getByText(/waiting for matching/i)).toBeInTheDocument();
  expect(screen.queryByText('UPDATE PREFERENCES')).toBeNull();
});
