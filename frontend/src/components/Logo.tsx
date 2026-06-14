/** ModelForge logomark — angular "M" twin forge-flames with a rising green spark. */
export function Logo({ size = 40, className }: { size?: number; className?: string }) {
  const id = "mf";
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-label="ModelForge">
      <defs>
        <linearGradient id={`${id}-tile`} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#16233b" />
          <stop offset="1" stopColor="#0b1322" />
        </linearGradient>
        <radialGradient id={`${id}-glow`} cx="0" cy="0" r="1" gradientTransform="translate(11 8) rotate(45) scale(26)" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22c55e" stopOpacity="0.30" />
          <stop offset="1" stopColor="#22c55e" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-stroke`} x1="8" y1="28" x2="32" y2="10" gradientUnits="userSpaceOnUse">
          <stop stopColor="#16a34a" />
          <stop offset="1" stopColor="#4ade80" />
        </linearGradient>
      </defs>

      {/* tile */}
      <rect x="0.5" y="0.5" width="39" height="39" rx="11" fill={`url(#${id}-tile)`} />
      <rect x="0.5" y="0.5" width="39" height="39" rx="11" fill={`url(#${id}-glow)`} />
      <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="10.75" stroke="#22c55e" strokeOpacity="0.22" strokeWidth="1.5" />

      {/* angular M / twin forge-flames */}
      <path
        d="M9 28 L14.5 13 L20 21 L25.5 13 L31 28"
        stroke={`url(#${id}-stroke)`}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* rising spark */}
      <path
        d="M20 5.4 L21.15 8.1 L23.85 9.25 L21.15 10.4 L20 13.1 L18.85 10.4 L16.15 9.25 L18.85 8.1 Z"
        fill="#86efac"
      />
    </svg>
  );
}
