import { errorMessage } from './errors';

test("a server's error text reaches the user", () => {
  expect(errorMessage(new Error('Invalid email or password'))).toBe('Invalid email or password');
});

test('a fetch that got no answer shows the network message, not "Failed to fetch"', () => {
  expect(errorMessage(new TypeError('Failed to fetch'))).toBe('Network error. Please try again.');
});

test('anything without a message falls back to the network message', () => {
  expect(errorMessage(new Error(''))).toBe('Network error. Please try again.');
  expect(errorMessage('boom')).toBe('Network error. Please try again.');
});
