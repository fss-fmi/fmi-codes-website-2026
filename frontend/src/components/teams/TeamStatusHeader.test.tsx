import { render, screen } from '@testing-library/react';
import TeamStatusHeader from './TeamStatusHeader';
import type { Team } from '@/types/team';

const NO_SLOT = 'Your team holds no slot in the event. For any questions, contact the organizers.';

function renderHeader(team: Partial<Team>, frozen = false) {
  render(
    <TeamStatusHeader
      team={{ team_name: 'Night Owls', status: 'active', ...team }}
      memberCount={3}
      frozen={frozen}
    />,
  );
}

test.each([false, true])(
  'an active team with no slot and no queue place is told so (frozen: %s)',
  (frozen) => {
    renderHeader({ is_registered: false, queue_position: null }, frozen);
    expect(screen.getByText(`> ${NO_SLOT}`)).toBeInTheDocument();
  },
);

test.each([
  ['registered', { is_registered: true }],
  ['queued', { is_registered: false, queue_position: 2 }],
  ['pending', { status: 'pending', is_registered: false }],
])('a %s team gets no no-slot banner', (_case, team) => {
  renderHeader(team);
  expect(screen.queryByText(/holds no slot/)).toBeNull();
});

test('while frozen the queue banner sends questions to the organizers', () => {
  renderHeader({ is_registered: false, queue_position: 2 }, true);
  expect(
    screen.getByText(
      '> In the waiting queue at position #2. For any questions, contact the organizers.',
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText(/registered automatically/)).toBeNull();
});

test('before the freeze the queue banner promises a slot when one opens', () => {
  renderHeader({ is_registered: false, queue_position: 2 });
  expect(screen.getByText(/registered automatically when a slot opens/)).toBeInTheDocument();
});
