/**
 * Discord wordmark glyph, shared by the desktop ContactSection card and the
 * MobileHomePage primary-channel card. Size and fill are configurable so each
 * consumer can preserve its own dimensions and color.
 */
export default function DiscordIcon({
  size = 24,
  fill = 'var(--px-salmon)',
}: {
  size?: number;
  fill?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={fill}
      aria-hidden="true"
    >
      <path d="M20.317 4.369A19.79 19.79 0 0 0 16.558 3a13.5 13.5 0 0 0-.63 1.28 18.35 18.35 0 0 0-5.856 0A13.6 13.6 0 0 0 9.442 3a19.74 19.74 0 0 0-3.76 1.369C2.257 9.09 1.334 13.7 1.796 18.24a19.9 19.9 0 0 0 5.994 3.03 14.44 14.44 0 0 0 1.284-2.083 12.85 12.85 0 0 1-2.02-.976c.169-.124.335-.253.495-.386a14.15 14.15 0 0 0 12.902 0c.161.133.327.262.495.386-.646.386-1.324.71-2.021.977a14.5 14.5 0 0 0 1.284 2.082 19.85 19.85 0 0 0 5.995-3.03c.542-5.28-.926-9.85-3.887-13.87ZM8.02 15.478c-1.184 0-2.157-1.085-2.157-2.42 0-1.334.952-2.42 2.157-2.42s2.178 1.086 2.157 2.42c0 1.335-.952 2.42-2.157 2.42Zm7.96 0c-1.183 0-2.156-1.085-2.156-2.42 0-1.334.951-2.42 2.156-2.42s2.178 1.086 2.157 2.42c0 1.335-.952 2.42-2.157 2.42Z" />
    </svg>
  );
}
