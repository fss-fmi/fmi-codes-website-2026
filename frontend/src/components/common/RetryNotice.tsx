import FormAlert from './FormAlert';

/**
 * Explains a rate-limit countdown once, without the ticking number, so a screen reader
 * reads it a single time (WCAG 4.1.3). The status region stays mounted while idle: a
 * region that appears together with its text is often not announced.
 */
export default function RetryNotice({ waiting, action }: { waiting: boolean; action: string }) {
  return (
    <div role="status">
      {waiting && (
        <FormAlert
          kind="info"
          style={{ marginBottom: '12px' }}
        >
          Lots of people are {action} right now. We&apos;ll try again automatically when the
          countdown ends, so keep this page open. Changing a field stops the retry.
        </FormAlert>
      )}
    </div>
  );
}
