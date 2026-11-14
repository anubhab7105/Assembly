export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <span className={`cin-brand-mark ${className}`} aria-hidden="true">
      <svg viewBox="0 0 44 44" fill="none">
        <defs>
          <linearGradient id="assembly-loop-a" x1="6" y1="4" x2="38" y2="40" gradientUnits="userSpaceOnUse">
            <stop stopColor="#7cc4ff" />
            <stop offset="0.5" stopColor="#2f7bff" />
            <stop offset="1" stopColor="#8b5cf6" />
          </linearGradient>
          <linearGradient id="assembly-loop-b" x1="38" y1="6" x2="6" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="#9be7ff" />
            <stop offset="0.55" stopColor="#4f8dff" />
            <stop offset="1" stopColor="#7c5cff" />
          </linearGradient>
          <radialGradient id="assembly-core" cx="0" cy="0" r="1" gradientTransform="translate(22 22) rotate(90) scale(9)">
            <stop stopColor="#dbeaff" />
            <stop offset="1" stopColor="#6ea8ff" stopOpacity="0.15" />
          </radialGradient>
        </defs>
        <circle cx="22" cy="22" r="7.5" fill="url(#assembly-core)" opacity="0.9" />
        <ellipse cx="22" cy="22" rx="16.5" ry="8.1" stroke="url(#assembly-loop-a)" strokeWidth="2.4" />
        <ellipse cx="22" cy="22" rx="16.5" ry="8.1" stroke="url(#assembly-loop-b)" strokeWidth="2.4" transform="rotate(60 22 22)" />
        <ellipse cx="22" cy="22" rx="16.5" ry="8.1" stroke="url(#assembly-loop-a)" strokeWidth="2.4" transform="rotate(120 22 22)" />
        <circle cx="22" cy="22" r="3.1" fill="#eaf3ff" />
      </svg>
    </span>
  )
}
