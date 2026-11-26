import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MentorsPanel from './MentorsPanel';
import type { TeamMentor } from '@/types/team';

const prefs = [{ mentor_id: 4, rank: 1, mentor_name: 'Ana Petrova' }];

const PHOTO = '/mentorPictures/ana-petrova.webp';

function renderPanel(props: {
  isRegistered: boolean;
  isCaptain?: boolean;
  withPrefs?: boolean;
  preferencesOpen?: boolean;
  confirmed?: boolean | undefined;
  mentors?: TeamMentor[];
}) {
  render(
    <MemoryRouter>
      <MentorsPanel
        confirmed={'confirmed' in props ? props.confirmed : false}
        mentors={props.mentors ?? []}
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

test('once confirmed, a team that is not registered gets only the first sentence', () => {
  renderPanel({ isRegistered: false, confirmed: true });
  expect(
    screen.getByText('> Only registered teams take part in mentor matching.'),
  ).toBeInTheDocument();
  expect(screen.queryByText(/once it holds one of the event slots/)).toBeNull();
});

test('before confirmation, a team that is not registered hears it can rank once it has a slot', () => {
  renderPanel({ isRegistered: false });
  expect(screen.getByText(/once it holds one of the event slots/)).toBeInTheDocument();
});

test.each([true, false])(
  'a confirmed team with no mentors is told the organizers will assign them (ranked: %s)',
  (withPrefs) => {
    renderPanel({ isRegistered: true, confirmed: true, withPrefs });
    expect(
      screen.getByText("> The organizers haven't assigned mentors to your team yet."),
    ).toBeInTheDocument();
    expect(screen.queryByText('CHOOSE MENTORS')).toBeNull();
    expect(screen.queryByText(/waiting for matching/i)).toBeNull();
  },
);

test('the registration check comes before the no-mentors note', () => {
  renderPanel({ isRegistered: false, confirmed: true });
  expect(screen.queryByText(/haven't assigned mentors/)).toBeNull();
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

test('an assigned mentor shows the photo the frontend serves', () => {
  renderPanel({
    isRegistered: true,
    confirmed: true,
    mentors: [{ mentor_id: 4, mentor_name: 'Ana Petrova', picture_url: PHOTO }],
  });
  expect(screen.getByRole('img', { name: 'Ana Petrova' })).toHaveAttribute('src', PHOTO);
});

test('an assigned mentor without a photo gets no image', () => {
  renderPanel({
    isRegistered: true,
    confirmed: true,
    mentors: [{ mentor_id: 4, mentor_name: 'Ana Petrova', picture_url: null }],
  });
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByText('Ana Petrova')).toBeInTheDocument();
});

test('a new photo path shows even after the old one failed to load', () => {
  const panel = (picture_url: string) => (
    <MemoryRouter>
      <MentorsPanel
        confirmed
        mentors={[{ mentor_id: 4, mentor_name: 'Ana Petrova', picture_url }]}
        prefs={[]}
        isCaptain
        isRegistered
        preferencesOpen
      />
    </MemoryRouter>
  );
  const { rerender } = render(panel(PHOTO));
  fireEvent.error(screen.getByRole('img', { name: 'Ana Petrova' }));
  expect(screen.queryByRole('img')).toBeNull();

  rerender(panel('/mentorPictures/ana-petrova-new.webp'));
  expect(screen.getByRole('img', { name: 'Ana Petrova' })).toHaveAttribute(
    'src',
    '/mentorPictures/ana-petrova-new.webp',
  );
});
