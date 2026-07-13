import './world.css';

/* The dawn field: sky, layered ridges, a low sun, two birds. Fixed behind
   the page, purely decorative. Shared by the landing and the first-run
   place picker so the funnel reads as one continuous world. The data-*
   hooks are for the landing's scroll choreography; a static render (e.g.
   /start) just shows the dawn sky and the ridges, which is the point. */
export function World() {
  return (
    <div className="qb-world" aria-hidden="true">
      <div className="qb-sky qb-sky-dawn" />
      <div className="qb-sky qb-sky-morn" data-sky-morn />
      <div className="qb-wisp qb-wisp-1" />
      <div className="qb-wisp qb-wisp-2" />
      <div className="qb-haze" />
      <div className="qb-sun" data-sun />
      <svg className="qb-ridge qb-ridge-far" data-ridge-far viewBox="0 0 1440 320" preserveAspectRatio="none">
        <path d="M0 190 C 190 130, 400 168, 620 150 S 1010 96, 1230 132 S 1390 158 1440 148 L1440 320 L0 320 Z" fill="#EBE5D0" />
        <path d="M0 190 C 190 130, 400 168, 620 150 S 1010 96, 1230 132 S 1390 158 1440 148" fill="none" stroke="#CBC2A4" strokeWidth="1.4" opacity=".5" />
      </svg>
      <svg className="qb-ridge qb-ridge-mid" data-ridge-mid viewBox="0 0 1440 320" preserveAspectRatio="none">
        <path d="M0 226 C 250 184, 490 220, 730 202 S 1140 168, 1440 198 L1440 320 L0 320 Z" fill="#E0D9BF" />
        <path d="M0 226 C 250 184, 490 220, 730 202 S 1140 168, 1440 198" fill="none" stroke="#BFB595" strokeWidth="1.4" opacity=".5" />
      </svg>
      <svg className="qb-ridge qb-ridge-near" viewBox="0 0 1440 320" preserveAspectRatio="none">
        <path d="M0 258 C 270 232, 540 254, 800 242 S 1220 224, 1440 238 L1440 320 L0 320 Z" fill="#D2CAA9" />
        <path d="M0 258 C 270 232, 540 254, 800 242 S 1220 224, 1440 238" fill="none" stroke="#AC9F79" strokeWidth="1.5" opacity=".55" />
        <g stroke="#AC9F79" strokeWidth="1" strokeLinecap="round" opacity=".5">
          <path d="M150 262 l-13 10 M212 259 l-13 10 M274 259 l-13 10 M880 254 l-13 10 M942 252 l-13 10 M1240 246 l-13 10 M1302 244 l-13 10" />
        </g>
        <path d="M1178 246 V 208 M1178 213 h22 l7 6 -7 6 h-22 z" stroke="#8F8158" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity=".65" />
        <path d="M244 258 V 232 M244 236 h15 l5 4 -5 4 h-15 z" stroke="#9C8F66" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" opacity=".45" />
      </svg>
      <svg className="qb-birdsvg" viewBox="0 0 1440 160" preserveAspectRatio="xMidYMid slice">
        <g className="qb-bird qb-bird-a" stroke="#6C6250" fill="none" strokeWidth="1.5" strokeLinecap="round">
          <path d="M1052 72 q8 -9 16 0 q8 -9 16 0" />
        </g>
        <g className="qb-bird qb-bird-b" stroke="#6C6250" fill="none" strokeWidth="1.5" strokeLinecap="round">
          <path d="M1130 44 q6 -7 12 0 q6 -7 12 0" />
        </g>
      </svg>
    </div>
  );
}
