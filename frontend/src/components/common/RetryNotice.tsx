import FormAlert from './FormAlert';

/**
 * Explains a rate-limit countdown once, without the ticking number, so a screen reader
 * reads it a single time (WCAG 4.1.3). The status region stays mounted while idle: a
 * region that appears together with its text is often not announced. It sits below the
 * submit button, so the button the user just pressed doesn't move when the note appears.
 */
export default function RetryNotice({ retrying, action }: { retrying: boolean; action: string }) {
  return (
    <div role="status">
      {retrying && (
        <FormAlert
          kind="info"
          style={{ marginTop: '12px', marginBottom: 0 }}
        >
          Lots of people are {action} right now. We&apos;ll try again automatically when the
          countdown ends, so keep this page open. Changing a field stops the retry.
        </FormAlert>
      )}
    </div>
  );
}
