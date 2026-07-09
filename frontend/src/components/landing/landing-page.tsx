import { useEffect, useMemo, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Chip, QuestCard, SageButton, Stamp, StampDefs, verticals } from '@questboard/ui';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { CLIP_STATUS, shortDate, toBoardCard } from '@/utils/board-card';
import { verticalParams } from '@/utils/board-verticals';
import { hasEntered } from '@/lib/entry';
import { handleEnter, pickLandingCards, plainWords } from './landing-logic';
import type { ApplicationFilters, ApplicationResponse } from '@/types/application';
import './landing.css';

/* The front page, redesign A: the live board floats as a window over a coded
   dawn field, and the product performs itself (a card clips, the explain
   sheet answers) on a gentle loop. The cards inside the window are the real
   @questboard/ui QuestCard fed real board rows, and the demo text is built
   from those rows, so nothing here is a hardcoded fake that can drift. */

function BrandMark() {
  return (
    <div className="qb-land-topbar">
      <span className="qb-land-tile">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <g transform="rotate(-4 8 5.8)">
            <rect x="6.35" y="1.9" width="3.3" height="7.8" rx="1.65" fill="#FFFDF8" />
          </g>
          <circle cx="8" cy="12.5" r="1.95" fill="#FFFDF8" />
          <circle cx="8" cy="12.5" r="0.85" fill="#A6522E" />
        </svg>
      </span>
      <b>Questboard</b>
    </div>
  );
}

/* The dawn field, fixed behind the page: sky, sun, layered ridges, birds. */
function World() {
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

/* One real board card; Clip writes through the real status mutation. */
function LandingCard({ app, labels }: { app: ApplicationResponse; labels: Record<string, string> }) {
  const updateStatus = useUpdateStatus();
  const card = toBoardCard(app, resolveSourceLabel(app.source, labels));
  return (
    <QuestCard
      vertical={card.vertical}
      title={card.title}
      href={card.href}
      meta={card.meta}
      needs={card.needs}
      firstQuest={card.firstQuest}
      pay={card.pay}
      payUnit={card.payUnit}
      applied={card.applied}
      clippedDate={card.clippedDate}
      onClip={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
    />
  );
}

/* A window-chrome chip whose count is the query's true total. */
function ChromeChip({ label, filters }: { label: string; filters: Partial<ApplicationFilters> }) {
  const { data } = useApplications({ ...filters, page: 1, page_size: 1 });
  return <Chip label={label} count={data?.total} dim={data !== undefined && data.total < 3} />;
}

/* Split a number into fixed digit cells for the odometer. */
function OdoGroup({ value, label }: { value: number; label: string }) {
  const digits = String(value).split('');
  return (
    <div className="qb-odo-group">
      <div className="qb-odo-cells qb-scene-obj" data-odo-target={value}>
        {digits.map((d, i) => (
          <span key={i} className="qb-flapcell">
            {d}
          </span>
        ))}
      </div>
      <span className="qb-odo-lab qb-scene-obj">{label}</span>
    </div>
  );
}

const STRIP_VERTICALS = ['career', 'camera', 'study', 'lens', 'party'] as const;

export function LandingPage() {
  const navigate = useNavigate();
  const labels = useSourceLabels();
  const entered = hasEntered();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = 'Questboard, one board for every side quest';
  }, []);

  const boardTotal = useApplications({ ...verticalParams('all'), page: 1, page_size: 1 }).data?.total;
  const pay500Total = useApplications({
    ...verticalParams('all'),
    salary_min: 500,
    page: 1,
    page_size: 1,
  }).data?.total;

  /* one board page of the newest rows: enough spread for mixed verticals */
  const newest = useApplications({
    ...verticalParams('all'),
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 24,
  });
  const items = newest.data?.items ?? [];
  const pinned = pickLandingCards(items);

  /* the explain-sheet script, built from the real pinned rows so it can
     never say something the cards do not. one entry per card, in order. */
  const explains = useMemo(
    () =>
      pinned.map((app, i) => ({
        card: i,
        ...plainWords(app, resolveSourceLabel(app.source, labels)),
      })),
    [pinned, labels],
  );

  const enter = () => handleEnter(navigate);
  const ctaLabel = entered ? 'Back to the board' : 'Open the board';

  /* ---- motion + demo choreography, once the pinned cards exist ---- */
  const explainsRef = useRef(explains);
  useEffect(() => {
    explainsRef.current = explains;
  }, [explains]);
  const ready = pinned.length > 0 && boardTotal !== undefined;

  useEffect(() => {
    if (!ready) return;
    const root = rootRef.current;
    if (!root) return;
    const q = <T extends Element>(s: string) => root.querySelector<T>(s);
    const docEl = document.documentElement;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)');
    const wide = window.matchMedia('(min-width: 881px)');
    const motionOK = () => !reduce.matches;

    let raf = 0;
    const jobs = new Set<(t: number, dt: number) => boolean>();
    let lastT = 0;
    const loop = (t: number) => {
      if (!jobs.size) return;
      const dt = Math.min((t - lastT) / 1000, 1 / 30);
      lastT = t;
      jobs.forEach((j) => {
        if (j(t, dt) === false) jobs.delete(j);
      });
      raf = requestAnimationFrame(loop);
    };
    const addJob = (j: (t: number, dt: number) => boolean) => {
      if (jobs.has(j)) return;
      jobs.add(j);
      if (jobs.size === 1) {
        lastT = performance.now();
        raf = requestAnimationFrame(loop);
      }
    };
    const countUp = (target: number, dur: number, render: (v: number, done: boolean) => void) => {
      let start: number | null = null;
      addJob((t) => {
        if (start === null) start = t;
        const p = Math.min(1, (t - start) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        render(Math.round(e * target), p >= 1);
        return p < 1;
      });
    };

    /* world lighting + parallax */
    const skyMorn = q<HTMLElement>('[data-sky-morn]');
    const sun = q<HTMLElement>('[data-sun]');
    const rFar = q<HTMLElement>('[data-ridge-far]');
    const rMid = q<HTMLElement>('[data-ridge-mid]');
    let worldDirty = true;
    const worldJob = () => {
      if (!worldDirty) return false;
      worldDirty = false;
      const max = docEl.scrollHeight - window.innerHeight;
      const wp = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      if (skyMorn) skyMorn.style.opacity = wp.toFixed(3);
      if (sun) sun.style.transform = `translateY(${(-(wp * window.innerHeight * 0.2)).toFixed(1)}px)`;
      if (rFar) rFar.style.transform = `translateY(${(wp * 16).toFixed(1)}px)`;
      if (rMid) rMid.style.transform = `translateY(${(wp * 8).toFixed(1)}px)`;
      return true;
    };
    const onScroll = () => {
      worldDirty = true;
      addJob(worldJob);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    addJob(worldJob);

    /* reveals */
    const runOdo = (scope: Element, animate: boolean) => {
      scope.querySelectorAll<HTMLElement>('[data-odo-target]').forEach((group, gi) => {
        const target = parseInt(group.getAttribute('data-odo-target') || '0', 10);
        const cells = group.querySelectorAll<HTMLElement>('.qb-flapcell');
        const paint = (v: number) => {
          let s = String(v);
          while (s.length < cells.length) s = '0' + s;
          cells.forEach((c, i) => (c.textContent = s.charAt(i)));
        };
        if (!animate) {
          paint(target);
          return;
        }
        paint(0);
        window.setTimeout(() => {
          countUp(target, 1300, (v, done) => {
            paint(v);
            if (done)
              cells.forEach((c, i) => window.setTimeout(() => c.classList.add('qb-seat'), i * 45));
          });
        }, 250 + gi * 220);
      });
    };
    const trigger = (el: Element) => {
      if (el.classList.contains('go')) return;
      el.classList.add('go');
      if (el.hasAttribute('data-odo')) runOdo(el, motionOK());
    };
    const reveals = Array.from(root.querySelectorAll('[data-reveal]'));
    let io: IntersectionObserver | null = null;
    if (!motionOK() || !('IntersectionObserver' in window)) {
      reveals.forEach(trigger);
    } else {
      io = new IntersectionObserver(
        (entries) =>
          entries.forEach((en) => {
            if (en.isIntersecting) {
              trigger(en.target);
              io?.unobserve(en.target);
            }
          }),
        { threshold: 0.01, rootMargin: '0px 0px -110px 0px' },
      );
      reveals.forEach((t) => {
        const r = t.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) trigger(t);
        else io?.observe(t);
      });
    }

    /* board-window tilt */
    const win = q<HTMLElement>('[data-board-window]');
    let tiltCleanup: (() => void) | null = null;
    if (win && motionOK() && fine.matches && wide.matches) {
      const s = { rx: 0, ry: 0, vrx: 0, vry: 0, trx: 0, tryy: 0 };
      let rect: DOMRect | null = null;
      const K = 120;
      const C = 18;
      const BASE = 3;
      const job = (_t: number, dt: number) => {
        let settled = true;
        s.vrx += (K * (s.trx - s.rx) - C * s.vrx) * dt;
        s.rx += s.vrx * dt;
        s.vry += (K * (s.tryy - s.ry) - C * s.vry) * dt;
        s.ry += s.vry * dt;
        if (
          Math.abs(s.trx - s.rx) > 0.004 ||
          Math.abs(s.vrx) > 0.004 ||
          Math.abs(s.tryy - s.ry) > 0.004 ||
          Math.abs(s.vry) > 0.004
        )
          settled = false;
        if (settled && s.trx === 0 && s.tryy === 0) {
          win.style.transform = '';
          return false;
        }
        win.style.transform = `rotateX(${(BASE + s.rx).toFixed(3)}deg) rotateY(${s.ry.toFixed(3)}deg)`;
        return true;
      };
      const onEnter = () => {
        rect = win.getBoundingClientRect();
      };
      const onMove = (ev: PointerEvent) => {
        if (!rect) return;
        const dx = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
        const dy = ((ev.clientY - rect.top) / rect.height) * 2 - 1;
        s.trx = Math.max(-1.6, Math.min(1.6, -dy * 1.6));
        s.tryy = Math.max(-2.2, Math.min(2.2, dx * 2.2));
        addJob(job);
      };
      const onLeave = () => {
        rect = null;
        s.trx = 0;
        s.tryy = 0;
        addJob(job);
      };
      win.addEventListener('pointerenter', onEnter);
      win.addEventListener('pointermove', onMove);
      win.addEventListener('pointerleave', onLeave);
      tiltCleanup = () => {
        win.removeEventListener('pointerenter', onEnter);
        win.removeEventListener('pointermove', onMove);
        win.removeEventListener('pointerleave', onLeave);
      };
    }

    /* the hero demo: a card clips, the explain sheet answers, looping */
    const body = q<HTMLElement>('[data-board-body]');
    const ghost = q<HTMLElement>('[data-ghost]');
    const mark = q<HTMLElement>('[data-mark]');
    const ring = q<HTMLElement>('[data-ring]');
    const sheet = q<HTMLElement>('[data-sheet]');
    const sheetKicker = q<HTMLElement>('[data-sheet-kicker]');
    const sheetText = q<HTMLElement>('[data-sheet-text]');
    const sheetBar = q<HTMLElement>('[data-sheet-bar]');
    const slots = Array.from(root.querySelectorAll<HTMLElement>('.qb-land-slot'));
    let timers: number[] = [];
    let typeTimer = 0;
    let dead = false;
    let heroVisible = true;

    const after = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms));
    const clearDemo = () => {
      timers.forEach(clearTimeout);
      timers = [];
      if (typeTimer) {
        clearInterval(typeTimer);
        typeTimer = 0;
      }
    };
    const offsetIn = (el: HTMLElement, anc: HTMLElement) => {
      let x = 0;
      let y = 0;
      let e: HTMLElement | null = el;
      while (e && e !== anc) {
        x += e.offsetLeft;
        y += e.offsetTop;
        e = e.offsetParent as HTMLElement | null;
      }
      return { x, y };
    };
    const ghostTo = (x: number, y: number, ms: number) => {
      if (!ghost) return;
      ghost.style.transitionDuration = `${ms}ms, .35s`;
      ghost.style.transform = `translate(${Math.round(x)}px,${Math.round(y)}px)`;
    };
    const ghostJump = (x: number, y: number) => {
      if (!ghost) return;
      ghost.style.transitionDuration = '0ms, .35s';
      ghost.style.transform = `translate(${Math.round(x)}px,${Math.round(y)}px)`;
      void ghost.offsetWidth;
    };
    const placeMark = (idx: number) => {
      if (!body || !mark || !ring || !slots[idx]) return;
      const p = offsetIn(slots[idx], body);
      const w = slots[idx].offsetWidth;
      const h = slots[idx].offsetHeight;
      mark.style.left = `${p.x + w - 86}px`;
      mark.style.top = `${p.y + h - 30}px`;
      ring.style.left = `${p.x + w - 88}px`;
      ring.style.top = `${p.y + h - 32}px`;
      ring.style.width = '92px';
      ring.style.height = '26px';
    };
    const placeSheet = (idx: number) => {
      if (!body || !sheet || !slots[idx]) return;
      const p = offsetIn(slots[idx], body);
      sheet.dataset.card = String(idx);
      sheet.style.left = `${p.x}px`;
      sheet.style.top = `${p.y}px`;
      sheet.style.width = `${slots[idx].offsetWidth}px`;
      sheet.style.minHeight = `${slots[idx].offsetHeight}px`;
    };
    const fillSheet = (ex: (typeof explainsRef.current)[number]) => {
      if (sheetKicker) sheetKicker.textContent = ex.kicker;
    };
    const typeText = (str: string) => {
      if (!sheetText) return;
      let i = 0;
      sheetText.textContent = '';
      sheetText.classList.add('typing');
      typeTimer = window.setInterval(() => {
        i += 2;
        sheetText.textContent = str.slice(0, i);
        if (i >= str.length) {
          clearInterval(typeTimer);
          typeTimer = 0;
          sheetText.classList.remove('typing');
        }
      }, 28);
    };
    const resetDemo = () => {
      mark?.classList.remove('stamped');
      ring?.classList.remove('stamped');
      slots[0]?.classList.remove('dip');
      sheet?.classList.remove('open', 'hold', 'closing');
      if (sheetBar) sheetBar.style.width = '';
      ghost?.classList.remove('gshow', 'gpress');
    };

    let exIdx = 0;
    const play = () => {
      if (dead || !motionOK()) return;
      if (document.hidden || !heroVisible) {
        after(1200, play);
        return;
      }
      const list = explainsRef.current;
      if (!list.length || !body) return;
      resetDemo();
      const ex = list[exIdx % list.length];
      let t = 0;

      /* phase 1: the ghost clips the first card, the postmark presses */
      after((t += 150), () => {
        if (!body) return;
        ghostJump(body.offsetWidth - 30, -16);
        ghost?.classList.add('gshow');
        placeMark(0);
        const p = offsetIn(slots[0], body);
        ghostTo(p.x + slots[0].offsetWidth - 60, p.y + slots[0].offsetHeight - 20, 950);
      });
      after((t += 1250), () => ghost?.classList.add('gpress'));
      after((t += 140), () => {
        ghost?.classList.remove('gpress');
        slots[0]?.classList.add('dip');
        mark?.classList.add('stamped');
        ring?.classList.add('stamped');
      });

      /* phase 2: the explain sheet slides up over a card and types */
      after((t += 1450), () => {
        if (!body || !slots[ex.card]) return;
        const p = offsetIn(slots[ex.card], body);
        ghostTo(p.x + slots[ex.card].offsetWidth * 0.55, p.y + slots[ex.card].offsetHeight * 0.45, 850);
      });
      after((t += 1000), () => {
        ghost?.classList.remove('gshow');
        placeSheet(ex.card);
        fillSheet(ex);
        if (sheetText) sheetText.textContent = '';
        sheet?.classList.add('open');
      });
      after((t += 420), () => typeText(ex.text));
      const typeMs = Math.ceil(ex.text.length / 2) * 28 + 200;

      /* phase 3: the sheet holds, then closes and the loop advances */
      after((t += typeMs + 250), () => {
        sheet?.style.setProperty('--holdms', '3000ms');
        sheet?.classList.add('hold');
      });
      after((t += 3100), () => {
        sheet?.classList.remove('open', 'hold');
        sheet?.classList.add('closing');
      });
      after((t += 450), () => {
        sheet?.classList.remove('closing');
        if (sheetBar) sheetBar.style.width = '0px';
        mark?.classList.remove('stamped');
        ring?.classList.remove('stamped');
        slots[0]?.classList.remove('dip');
      });
      after((t += 950), () => {
        exIdx++;
        play();
      });
    };

    /* pause hygiene */
    const hero = q<HTMLElement>('[data-hero]');
    const world = q<HTMLElement>('.qb-world');
    const syncVis = () => world?.classList.toggle('qb-paused', document.hidden);
    document.addEventListener('visibilitychange', syncVis);
    let heroIO: IntersectionObserver | null = null;
    if (hero && 'IntersectionObserver' in window) {
      heroIO = new IntersectionObserver((entries) => (heroVisible = entries[0].isIntersecting), {
        threshold: 0,
      });
      heroIO.observe(hero);
    }

    const finalize = () => {
      dead = true;
      clearDemo();
      resetDemo();
      reveals.forEach(trigger);
      root.querySelectorAll<HTMLElement>('[data-odo-target]').forEach((g) => {
        const v = String(parseInt(g.getAttribute('data-odo-target') || '0', 10));
        g.querySelectorAll<HTMLElement>('.qb-flapcell').forEach((c, i) => {
          let s = v;
          while (s.length < g.querySelectorAll('.qb-flapcell').length) s = '0' + s;
          c.textContent = s.charAt(i);
        });
      });
      const list = explainsRef.current;
      if (list.length) {
        placeMark(0);
        mark?.classList.add('stamped');
        ring?.classList.remove('stamped');
        placeSheet(list[0].card);
        fillSheet(list[0]);
        if (sheetText) sheetText.textContent = list[0].text;
        sheet?.classList.add('open');
      }
    };

    /* boot */
    docEl.classList.add('qb-motion');
    if (!motionOK()) {
      finalize();
    } else {
      requestAnimationFrame(() => hero?.classList.add('go'));
      const b1 = window.setTimeout(() => hero?.classList.add('win-go'), 250);
      const b2 = window.setTimeout(play, 900);
      timers.push(b1, b2);
    }
    const onReduceChange = (e: MediaQueryListEvent) => {
      if (e.matches) finalize();
    };
    reduce.addEventListener('change', onReduceChange);

    return () => {
      dead = true;
      clearDemo();
      cancelAnimationFrame(raf);
      jobs.clear();
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      document.removeEventListener('visibilitychange', syncVis);
      reduce.removeEventListener('change', onReduceChange);
      io?.disconnect();
      heroIO?.disconnect();
      tiltCleanup?.();
    };
  }, [ready]);

  return (
    <div className="qb-page qb-landing" ref={rootRef}>
      <StampDefs />
      <World />

      <div className="qb-land-page">
        <div className="qb-land-hero" data-hero>
          <div className="qb-lwrap">
            <BrandMark />
            <h1>start side questing.</h1>
            <p className="qb-lsub">Real quests that actually pay, pulled live from real sources.</p>
            <div className="qb-land-cta">
              <SageButton big onClick={enter}>
                {ctaLabel}
              </SageButton>
              <span className="qb-lnote">Free. Your log lives in your browser.</span>
            </div>
          </div>

          <div className="qb-winpersp">
            <div className="qb-board-window" data-board-window>
              <div className="qb-win-chrome">
                <span className="qb-win-title">The board</span>
                <div className="qb-win-chips">
                  <ChromeChip label="career" filters={verticalParams('career')} />
                  <ChromeChip label="on camera" filters={verticalParams('camera')} />
                  <ChromeChip label="paid studies" filters={verticalParams('study')} />
                  <ChromeChip
                    label="$500 or more"
                    filters={{ ...verticalParams('all'), salary_min: 500 }}
                  />
                </div>
              </div>
              <div className="qb-board-body" data-board-body>
                {pinned.map((app) => (
                  <div key={app.id} className="qb-land-slot">
                    <LandingCard app={app} labels={labels} />
                  </div>
                ))}
                <span className="qb-demo-ring" data-ring aria-hidden="true" />
                <span className="qb-demo-mark" data-mark aria-hidden="true">
                  Clipped, {shortDate(new Date().toISOString()) ?? 'today'}
                </span>
                <div className="qb-demo-sheet" data-sheet aria-hidden="true">
                  <div className="qb-sheet-kicker" data-sheet-kicker />
                  <div className="qb-sheet-head">In plain words</div>
                  <div className="qb-sheet-text" data-sheet-text />
                  <div className="qb-sheet-method">Pulled from the posting.</div>
                  <span className="qb-sheet-bar" data-sheet-bar />
                </div>
                <svg className="qb-ghost" data-ghost width="26" height="30" viewBox="0 0 26 30" aria-hidden="true">
                  <path
                    d="M3 2 L3 23 L9 18 L13 27 L16 26 L12 17 L20 17 Z"
                    fill="#1C1B17"
                    stroke="#fff"
                    strokeWidth="1.4"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
            <div className="qb-win-ground" aria-hidden="true" />
          </div>
        </div>

        <div className="qb-scene qb-scene-ledger" data-reveal>
          <p className="qb-scap">The log counts only what paid.</p>
          <div className="qb-ledger-card qb-on-field qb-scene-obj">
            <div className="qb-done-label">Done</div>
            <div className="qb-dline">
              <span className="qb-dd">Jul 3</span>
              <span className="qb-dt">Prolific study batch paid out.</span>
              <span className="qb-dn">$45. Took 13 days.</span>
            </div>
            <div className="qb-dline">
              <span className="qb-dd">Jun 28</span>
              <span className="qb-dt">Did a paid snack focus group.</span>
              <span className="qb-dn">$125.</span>
            </div>
            <div className="qb-dline">
              <span className="qb-dd">Mar 4</span>
              <span className="qb-dt">Ran the 10k.</span>
              <span className="qb-dn">Helped by your sister.</span>
            </div>
            <div className="qb-ledger-total">
              <span className="qb-total-text">
                Paid out in <span className="qb-num">2026</span> so far:{' '}
                <span className="qb-num">$170</span>. Counting only what landed.
              </span>
            </div>
          </div>
        </div>

        {boardTotal !== undefined && pay500Total !== undefined && (
          <div className="qb-scene" data-reveal data-odo>
            <p className="qb-scap">Real quests, counted live.</p>
            <div className="qb-odo-card qb-on-field qb-scene-obj">
              <OdoGroup value={boardTotal} label="on the board right now" />
              <OdoGroup value={pay500Total} label="pay $500 or more" />
            </div>
          </div>
        )}

        <div className="qb-scene qb-scene-stamps" data-reveal>
          <p className="qb-scap">One board, every kind of quest.</p>
          <div className="qb-stamp-card qb-on-field qb-scene-obj">
            {STRIP_VERTICALS.map((v) => (
              <div key={v} className="qb-st" style={{ color: verticals[v].hue }}>
                <Stamp vertical={v} size={52} inheritColor />
                <span className="qb-lab">{verticals[v].label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="qb-land-foot">
          <p className="qb-fnote">The board restocks daily. Every listing links straight to the source.</p>
          <SageButton big onClick={enter}>
            {ctaLabel}
          </SageButton>
        </div>
      </div>
    </div>
  );
}
