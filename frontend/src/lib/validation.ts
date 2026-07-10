export const MIN_PASSWORD_LENGTH = 12;

/**
 * Validate a new-password / confirm-password pair for the auth forms.
 * Returns an error message string, or null when the pair is valid.
 * Kept in sync with the backend check in app/routes/auth.py.
 */
export function validateNewPassword(newPassword: string, confirmPassword: string): string | null {
  if (newPassword.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (newPassword !== confirmPassword) {
    return 'Passwords do not match.';
  }
  return null;
}
