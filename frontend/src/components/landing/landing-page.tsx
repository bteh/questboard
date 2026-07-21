import { useEffect, useMemo, useRef } from 'react';
import { Chip, KindStamp, Poster } from '@questboard/ui';
import { KINDS } from '@questboard/kinds';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { shortDate } from '@/utils/board-card';
import { toPoster } from '@/features/board/poster-model';
import { World } from './world';
import { plainWords } from './landing-logic';
import { DownloadOrNotify } from './download-cta';
import {
  SNAPSHOT_AS_OF,
  SNAPSHOT_CAREER,
  SNAPSHOT_HERO,
  SNAPSHOT_SOURCE_LABELS,
  SNAPSHOT_TOTALS,
} from './snapshot';
import type { ApplicationResponse } from '@/types/application';
import './landing.css';

/* The public front door for Questboard for Mac. It tells the story and
   points at the download; the app does the work. Path A runs locally, so
   this page ships with no backend: the felt-board window and the counters
   are fed by a FROZEN snapshot of real board rows (see snapshot.ts), never
   live hooks that a stranger's browser can't reach. The posters are the
   real @questboard/ui Poster through the same poster-model the board route
   uses, so design changes reflect here and nothing is a hardcoded fake. */

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
      <nav className="qb-land-nav">
        <a href="#how">How it works</a>
        <a href="#pricing">Pricing</a>
        <a href="#get">Get it</a>
      </nav>
    </div>
  );
}

/* One real snapshot poster through the board's own model. On this page the
   Clip control has no local board to write to, so it nudges toward the
   download instead of a dead mutation. The fit line never shows here: no
   resume has been compared, so a "covers N of M" claim would be invented. */
function SnapshotPoster({
  app,
  labels,
  onClip,
}: {
  app: ApplicationResponse;
  labels: Record<string, string>;
  onClip?: () => void;
}) {
  const poster = toPoster(app, resolveSourceLabel(app.source, labels));
  const { card } = poster;
  return (
    <Poster
      kind={poster.kind}
      title={card.title}
      href={card.href}
      giver={card.meta}
      desc={poster.desc}
      bring={poster.copy.bring}
      bringFree={poster.copy.bringFree}
      catchLine={poster.copy.catchLine}
      tags={poster.tags}
      pay={card.pay}
      payUnit={card.payUnit}
      applied={card.applied}
      clippedDate={card.clippedDate}
      rotateDeg={poster.rotateDeg}
      giverLogoUrl={poster.logoUrl}
      logoWell={poster.logoWell}
      onClip={onClip}
    />
  );
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

const scrollToGet = () =>
  document.getElementById('get')?.scrollIntoView({ behavior: 'smooth', block: 'center' });

export function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = 'Questboard for Mac, one board for real work and paid side quests';
  }, []);

  const labels = SNAPSHOT_SOURCE_LABELS;
  /* exactly three real side-quest rows, in a fixed order (no live query) */
  const pinned = SNAPSHOT_HERO;

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

  /* ---- motion + demo choreography (unchanged from the live board hero) ---- */
  const explainsRef = useRef(explains);
  useEffect(() => {
    explainsRef.current = explains;
  }, [explains]);
  const ready = pinned.length > 0;

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
    const clipRect = (idx: number) => {
      const slot = slots[idx];
      if (!body || !slot) return null;
      const clip = slot.querySelector<HTMLElement>('.qb-poster-clip');
      if (clip) {
        const p = offsetIn(clip, body);
        return { x: p.x, y: p.y, w: clip.offsetWidth, h: clip.offsetHeight };
      }
      const p = offsetIn(slot, body);
      return { x: p.x + slot.offsetWidth - 62, y: p.y + 20, w: 44, h: 22 };
    };
    const placeMark = (idx: number) => {
      if (!mark || !ring) return;
      const c = clipRect(idx);
      if (!c) return;
      mark.style.left = `${c.x + c.w - 98}px`;
      mark.style.top = `${c.y - 1}px`;
      ring.style.left = `${c.x - 5}px`;
      ring.style.top = `${c.y - 4}px`;
      ring.style.width = `${c.w + 10}px`;
      ring.style.height = `${c.h + 8}px`;
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

      after((t += 150), () => {
        if (!body) return;
        ghostJump(body.offsetWidth - 30, -16);
        ghost?.classList.add('gshow');
        placeMark(0);
        const c = clipRect(0);
        if (c) ghostTo(c.x + c.w * 0.55, c.y + c.h * 0.6, 950);
      });
      after((t += 1250), () => ghost?.classList.add('gpress'));
      after((t += 140), () => {
        ghost?.classList.remove('gpress');
        slots[0]?.classList.add('dip');
        mark?.classList.add('stamped');
        ring?.classList.add('stamped');
      });

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
      <World />

      <div className="qb-land-page">
        {/* ============================ HERO ============================ */}
        <div className="qb-land-hero" data-hero>
          <div className="qb-lwrap">
            <BrandMark />
            <p className="qb-eyebrow">A desktop app for Mac</p>
            <h1>Find real work and paid side quests.</h1>
            <p className="qb-lsub">
              A radar that runs on your Mac. It finds fresh opportunities, filters them hard, and
              keeps a link straight to the source. When you want a read on one, the AI you already
              use does the thinking. No account, and no AI bill from us.
            </p>
            <div className="qb-land-cta">
              <DownloadOrNotify big />
              <a className="qb-lsecondary" href="#how">
                See how it works
              </a>
            </div>
            <p className="qb-ltrust">No account. Nothing leaves your Mac unless you say so.</p>
          </div>

          <div className="qb-winpersp">
            <div className="qb-board-window" data-board-window>
              <div className="qb-win-chrome">
                <span className="qb-win-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="qb-win-title">Questboard</span>
                <div className="qb-win-chips">
                  <Chip label="tell them what you think" />
                  <Chip label="join a study" />
                  <Chip label="look after" />
                </div>
              </div>
              <div className="qb-board-body" data-board-body>
                {pinned.map((app) => (
                  <div key={app.id} className="qb-land-slot">
                    <SnapshotPoster app={app} labels={labels} onClip={scrollToGet} />
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

        {/* ========================= TRUST STRIP ========================= */}
        <div className="qb-lwrap">
          <div className="qb-trust-strip" data-reveal>
            <div className="qb-trust-item qb-scene-obj">
              <b>Runs on your Mac</b>
              <span>A desktop app, not a website. Your board and your log live locally.</span>
            </div>
            <div className="qb-trust-item qb-scene-obj">
              <b>Bring your own AI</b>
              <span>Connect Claude or Codex for the reading help. Or use none and still find work.</span>
            </div>
            <div className="qb-trust-item qb-scene-obj">
              <b>We never charge for AI</b>
              <span>The reading runs on your own plan. We never see your key or your resume.</span>
            </div>
            <div className="qb-trust-item qb-scene-obj">
              <b>Real, or it isn’t here</b>
              <span>Stated pay, true source, honest freshness. Unknowns stay unknown.</span>
            </div>
          </div>
        </div>

        {/* ========================= WHAT IT IS ========================= */}
        <div className="qb-scene qb-scene-lede" data-reveal>
          <p className="qb-scap">One board for every way to earn on the side.</p>
          <p className="qb-lede qb-scene-obj">
            Questboard watches the places real opportunities show up. Job boards, focus-group panels,
            casting calls, study registries, sitting marketplaces, grant calls. It pulls the fresh
            ones onto one board, checks the hard facts (still live, where it applies, what it pays),
            and keeps a link straight back to the source. It runs on your machine, and your data
            stays there.
          </p>
        </div>

        {/* ======================= TWO WORKFLOWS ======================= */}
        <div className="qb-scene qb-scene-flows qb-scene-stamps" data-reveal>
          <p className="qb-scap">Two ways in. One board.</p>
          <div className="qb-flows">
            <div className="qb-flow-col qb-scene-obj">
              <div className="qb-flow-copy">
                <h3>Find Work</h3>
                <p>
                  Career openings, pulled fresh and filtered by what actually rules you in or out:
                  location, remote scope, work authorization, pay, seniority. For a fit read, your
                  own AI compares the posting to your resume, point by point. We never upload the
                  resume, and we never charge for the AI.
                </p>
              </div>
              <div className="qb-flow-poster">
                <SnapshotPoster app={SNAPSHOT_CAREER} labels={labels} onClip={scrollToGet} />
              </div>
            </div>
            <div className="qb-flow-col qb-scene-obj">
              <div className="qb-flow-copy">
                <h3>Side Quests</h3>
                <p>
                  Paid studies, focus groups, casting calls, sitting gigs, grants, bank bonuses, and
                  more. No resume needed. Each one shows the pay it stated and links straight to
                  where you take it.
                </p>
              </div>
              <div className="qb-flow-poster">
                <SnapshotPoster app={pinned[0]} labels={labels} onClip={scrollToGet} />
              </div>
            </div>
          </div>
          <div className="qb-stamp-card qb-on-field qb-scene-obj">
            {KINDS.map((k, i) => (
              <div key={k.id} className="qb-st" style={{ ['--sd' as string]: `${0.15 + i * 0.05}s` }}>
                <KindStamp kind={k.id} size={44} />
                <span className="qb-lab">{k.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ==================== CONNECT YOUR AGENT ==================== */}
        <div className="qb-scene qb-scene-how" id="how" data-reveal>
          <p className="qb-scap">The board does the finding. The AI is optional.</p>
          <div className="qb-steps qb-scene-obj">
            <div className="qb-step">
              <span className="qb-step-n">1</span>
              <div>
                <b>Download and open it.</b>
                <p>It’s a Mac app. No account, no setup wizard to fight through.</p>
              </div>
            </div>
            <div className="qb-step">
              <span className="qb-step-n">2</span>
              <div>
                <b>Restock the board.</b>
                <p>Questboard pulls fresh opportunities from real sources and filters them for you.</p>
              </div>
            </div>
            <div className="qb-step">
              <span className="qb-step-n">3</span>
              <div>
                <b>Connect an assistant, if you want the reading help.</b>
                <p>
                  Link an app you may already use (Claude, Codex, or Cursor). It reads postings with
                  you, checks them against your resume when you ask, and drafts notes. We never charge
                  for it and never see your key.
                </p>
              </div>
            </div>
          </div>
          <div className="qb-fears qb-scene-obj">
            <div className="qb-fear">
              <b>Do I need to be a programmer?</b>
              <p>No. It’s a Mac app you download. Connecting an assistant is a one-time step with a guided setup.</p>
            </div>
            <div className="qb-fear">
              <b>Do I need to pay for AI?</b>
              <p>Not to us. The core board needs no AI at all. The optional reading help runs on whatever AI plan you already have.</p>
            </div>
          </div>
          <p className="qb-fine qb-scene-obj">
            It connects over MCP, the standard way those apps plug into local tools.
          </p>
        </div>

        {/* =============== WHY NOT JUST A JOB BOARD =============== */}
        <div className="qb-scene qb-scene-why qb-scene-ledger" data-reveal>
          <p className="qb-scap">Not another job board.</p>
          <div className="qb-why-grid qb-scene-obj">
            <div className="qb-why">
              <b>Fresh, and it says so</b>
              <p>Every listing carries when it was first seen and where it came from. Stale and dead links get caught, not buried.</p>
            </div>
            <div className="qb-why">
              <b>Eligibility is a fact, not a guess</b>
              <p>Remote country scope, local rules, dates, and stated pay are real fields. Unknowns stay unknown.</p>
            </div>
            <div className="qb-why">
              <b>Receipts, not aggregation</b>
              <p>Every result links straight to the source. Direct application links win when we can resolve them.</p>
            </div>
            <div className="qb-why">
              <b>It remembers what paid</b>
              <p>Clip, apply, complete, get paid. Your log counts the money that actually landed.</p>
            </div>
          </div>

          <div className="qb-ledger-card qb-on-field qb-scene-obj">
            <div className="qb-done-label">
              Done <span className="qb-done-eg">an example log</span>
            </div>
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
              <span className="qb-dn">Just for the medal.</span>
            </div>
            <div className="qb-ledger-total">
              <span className="qb-total-text">
                Paid out in <span className="qb-num">2026</span> so far:{' '}
                <span className="qb-num">$170</span>. Counting only what landed.
              </span>
            </div>
          </div>
          <p className="qb-odo-asof qb-scene-obj">
            An example. Your log fills in on your Mac as you get paid.
          </p>
        </div>

        {/* ==================== COUNTS (snapshot) ==================== */}
        <div className="qb-scene" data-reveal data-odo>
          <p className="qb-scap">What the radar had found by then.</p>
          <div className="qb-odo-card qb-on-field qb-scene-obj">
            <OdoGroup value={SNAPSHOT_TOTALS.quests} label="quests on the board" />
            <OdoGroup value={SNAPSHOT_TOTALS.addedToday} label="added that day" />
          </div>
          <p className="qb-odo-asof qb-scene-obj">
            A snapshot from {SNAPSHOT_AS_OF}. The app refreshes this on your machine.
          </p>
        </div>

        {/* ========================= PRICING ========================= */}
        <div className="qb-scene qb-scene-price" id="pricing" data-reveal>
          <p className="qb-scap">Free to do the work. A one-time pass for the extras.</p>
          <div className="qb-price-cards qb-scene-obj">
            <div className="qb-price-card">
              <div className="qb-price-head">
                <h3>Free</h3>
                <span className="qb-price-tag">forever</span>
              </div>
              <p className="qb-price-sub">Everything that finds and tracks the work.</p>
              <ul className="qb-price-list">
                <li>Source discovery, hard filters, and dedup</li>
                <li>Freshness receipts and direct source links</li>
                <li>Your local board, log, and workflow history</li>
                <li>Connect your own AI assistant</li>
                <li>A signed Mac app that installs clean</li>
              </ul>
            </div>
            <div className="qb-price-card qb-price-pro">
              <div className="qb-price-head">
                <h3>Pro</h3>
                <span className="qb-price-tag">one-time pass</span>
              </div>
              <p className="qb-price-sub">Pays for convenience, never for access.</p>
              <ul className="qb-price-list">
                <li>Automatic updates</li>
                <li>Premium source packs</li>
                <li>Standing watches with digests</li>
                <li>A one-time pass, never a subscription</li>
              </ul>
            </div>
          </div>
          <p className="qb-price-oath qb-scene-obj">
            No ads. No employer money. No AI credits. And never a paywall before your first useful search.
          </p>
        </div>

        {/* ========================= GET IT ========================= */}
        <div className="qb-land-foot" id="get">
          <p className="qb-scap">Get the radar on your Mac.</p>
          <DownloadOrNotify big />
        </div>

        {/* ========================= FAQ ========================= */}
        <div className="qb-scene qb-scene-faq" data-reveal>
          <div className="qb-faq qb-scene-obj">
            <div className="qb-faq-q">
              <b>Which Macs?</b>
              <p>Apple Silicon and Intel, on recent macOS. The build is universal.</p>
            </div>
            <div className="qb-faq-q">
              <b>Which AI assistants?</b>
              <p>Any MCP client. Claude and Codex are the ones I test first. The board also works with none.</p>
            </div>
            <div className="qb-faq-q">
              <b>Do I pay for AI?</b>
              <p>Not to us. The board needs no AI. The optional reading help runs on your own AI plan.</p>
            </div>
            <div className="qb-faq-q">
              <b>Does my resume leave my Mac?</b>
              <p>
                Questboard never uploads it and never sees it. It stays in a local file and is read
                only when you ask. If your assistant is a cloud app like Claude or Codex, it reads
                the resume under your own account there, the same as anything you paste in yourself.
              </p>
            </div>
            <div className="qb-faq-q">
              <b>Where does my data live?</b>
              <p>On your Mac, in a local file. There’s no cloud account.</p>
            </div>
            <div className="qb-faq-q">
              <b>Windows or Linux?</b>
              <p>Mac first, others later. Leave your email and I’ll tell you when.</p>
            </div>
          </div>
          <p className="qb-fnote">Every listing links straight to the source. New ones land every day.</p>
        </div>
      </div>
    </div>
  );
}
