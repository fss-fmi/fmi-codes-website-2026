import { ApiError, errorMessage, GENERIC_ERROR, NETWORK_ERROR, NetworkError } from './errors';

test("a server's error text reaches the user", () => {
  expect(errorMessage(new ApiError(401, 'Invalid email or password'))).toBe(
    'Invalid email or password',
  );
});

test('no answer at all shows the network message', () => {
  expect(errorMessage(new NetworkError())).toBe(NETWORK_ERROR);
});

test('a bug in our own code shows the generic text, never its message or the network one', () => {
  expect(errorMessage(new TypeError("Cannot read properties of undefined (reading 'x')"))).toBe(
    GENERIC_ERROR,
  );
  expect(errorMessage(new Error('boom'))).toBe(GENERIC_ERROR);
  expect(errorMessage('boom')).toBe(GENERIC_ERROR);
});
