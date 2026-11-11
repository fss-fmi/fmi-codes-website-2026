import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MentorsPanel from './MentorsPanel';

const prefs = [{ mentor_id: 4, rank: 1, mentor_name: 'Ana Petrova' }];

function renderPanel(props: { isRegistered: boolean; isCaptain?: boolean; withPrefs?: boolean }) {
  render(
    <MemoryRouter>
      <MentorsPanel
        confirmed={false}
        mentors={[]}
        prefs={props.withPrefs ? prefs : []}
        isCaptain={props.isCaptain ?? true}
        isRegistered={props.isRegistered}
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
