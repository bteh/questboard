/* Hand-drawn postal stamp defs from the mock: 1.75px single-weight line,
   imperfect circles. Mount once per page; Stamp and PostmarkStamp reference
   these by id. */
export function StampDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <defs>
        <g id="qb-stamp-career">
          <path d="M17 2.6 A14.4 14.4 0 1 1 6.5 6.1" fill="none" strokeWidth="1.75" />
          <path d="M4.8 8.3 A14.4 14.4 0 0 1 15.2 2.7" fill="none" strokeWidth="1.75" strokeDasharray="3 2.4" />
          <circle cx="12.2" cy="21.8" r="1.5" fill="currentColor" stroke="none" />
          <path d="M13.6 20.4 L21.4 12.6 M15.9 11.9 H22 V18" fill="none" strokeWidth="1.75" />
        </g>
        <g id="qb-stamp-camera">
          <path d="M16.5 2.5 A14.4 14.4 0 1 1 5.8 5.6" fill="none" strokeWidth="1.75" />
          <path d="M4.4 7.9 A14.4 14.4 0 0 1 14 2.6" fill="none" strokeWidth="1.75" strokeDasharray="2.6 2.6" />
          <rect x="8.6" y="12.4" width="13" height="9" rx="1.4" fill="none" strokeWidth="1.75" />
          <path d="M9 12.5 L21.4 9.2 M11.6 11.8 l1.6 -2.8 M15.4 10.8 l1.6 -2.8 M19.2 9.8 l1.5 -2.6" fill="none" strokeWidth="1.75" />
        </g>
        <g id="qb-stamp-study">
          <path d="M18 3 A14.4 14.4 0 1 1 6 5.4" fill="none" strokeWidth="1.75" />
          <path d="M4.7 7.6 A14.4 14.4 0 0 1 15.5 2.7" fill="none" strokeWidth="1.75" strokeDasharray="3.2 2.2" />
          <path d="M9.4 10.6 h11.2 a1.6 1.6 0 0 1 1.6 1.6 v5.4 a1.6 1.6 0 0 1 -1.6 1.6 h-6.4 l-3.4 3 v-3 h-1.4 a1.6 1.6 0 0 1 -1.6 -1.6 v-5.4 a1.6 1.6 0 0 1 1.6 -1.6 z" fill="none" strokeWidth="1.75" />
          <path d="M12.4 14.9 l1.9 1.9 3.5 -3.7" fill="none" strokeWidth="1.75" />
        </g>
        <g id="qb-stamp-lens">
          <path d="M17.3 2.7 A14.4 14.4 0 1 1 6.2 5.9" fill="none" strokeWidth="1.75" />
          <path d="M4.7 8.2 A14.4 14.4 0 0 1 15 2.6" fill="none" strokeWidth="1.75" strokeDasharray="2.8 2.4" />
          <rect x="7.4" y="11" width="13.2" height="9.6" rx="1.6" fill="none" strokeWidth="1.75" />
          <path d="M11 11 l1.4 -2.2 h3.2 l1.4 2.2" fill="none" strokeWidth="1.75" strokeLinejoin="round" />
          <circle cx="14" cy="15.8" r="3" fill="none" strokeWidth="1.75" />
          <circle cx="18.6" cy="13.4" r=".9" fill="currentColor" stroke="none" />
        </g>
        <g id="qb-stamp-party">
          <path d="M17.3 2.7 A14.4 14.4 0 1 1 6.2 5.9" fill="none" strokeWidth="1.75" />
          <path d="M4.7 8.2 A14.4 14.4 0 0 1 15 2.6" fill="none" strokeWidth="1.75" strokeDasharray="2.8 2.4" />
          <rect x="11.1" y="9.4" width="5.8" height="10.6" rx="1" fill="none" strokeWidth="1.6" transform="rotate(-21 14 20)" />
          <rect x="11.1" y="9.4" width="5.8" height="10.6" rx="1" fill="none" strokeWidth="1.6" />
          <rect x="11.1" y="9.4" width="5.8" height="10.6" rx="1" fill="none" strokeWidth="1.6" transform="rotate(21 14 20)" />
          <path d="M12.6 12.2 h2.8" fill="none" strokeWidth="1.3" />
        </g>
        <g id="qb-stamp-personal">
          <path d="M17.2 2.7 A14.4 14.4 0 1 1 6.1 5.9" fill="none" strokeWidth="1.75" />
          <path d="M4.6 8.1 A14.4 14.4 0 0 1 14.8 2.6" fill="none" strokeWidth="1.75" strokeDasharray="2.8 2.4" />
          <path d="M9.4 22.6 l-3.5 1 1 -3.5 L16.6 9.4 a1.8 1.8 0 0 1 2.6 2.6 z" fill="none" strokeWidth="1.75" />
          <path d="M15.5 10.5 l2.4 2.4" fill="none" strokeWidth="1.75" />
          <path d="M14.8 23.6 h6.6" fill="none" strokeWidth="1.75" />
        </g>
      </defs>
    </svg>
  );
}
