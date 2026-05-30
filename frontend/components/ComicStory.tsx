'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';

const PANEL_SRC = [
  '/assets/comics/1.jpg',
  '/assets/comics/2.jpg',
  '/assets/comics/3.jpg',
  '/assets/comics/4.jpg',
  '/assets/comics/5.png',
  '/assets/comics/6.png',
];

const CAPTION_COUNT = 5;
const FRAME_SCALE = 0.62;

export default function ComicStory() {
  const zoneRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const zone = zoneRef.current;
    const canvas = canvasRef.current;
    const canvasWrap = canvasWrapRef.current;
    const progressBar = progressRef.current;
    const track = trackRef.current;
    if (!zone || !canvas || !canvasWrap || !track) return undefined;

    const ctxRaw = canvas.getContext('2d', { alpha: false });
    if (!ctxRaw) return undefined;
    const ctx: CanvasRenderingContext2D = ctxRaw;

    const canvasEl = canvas;
    const canvasWrapEl = canvasWrap;
    const trackEl = track;

    const panels = [...trackEl.querySelectorAll('.comic-panel')];
    const solutionPanel = trackEl.querySelector('.comic-panel--solution');
    const captionPanels = panels.slice(0, CAPTION_COUNT);

    const IMAGE_COUNT = PANEL_SRC.length;
    const images: HTMLImageElement[] = [];
    let loaded = 0;
    let smoothBeat = 0;
    let smoothSolution = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0;

    function resizeCanvas() {
      const w = canvasWrapEl.clientWidth;
      const h = canvasWrapEl.clientHeight;
      canvasEl.width = Math.round(w * dpr);
      canvasEl.height = Math.round(h * dpr);
      canvasEl.style.width = `${w}px`;
      canvasEl.style.height = `${h}px`;
    }

    function getFrameBounds() {
      const cw = canvasEl.width;
      const ch = canvasEl.height;
      const frameW = cw * FRAME_SCALE;
      const frameH = ch * FRAME_SCALE;
      return {
        frameW,
        frameH,
        frameX: (cw - frameW) / 2,
        frameY: (ch - frameH) / 2,
      };
    }

    function getScrollT() {
      const top = window.scrollY + trackEl.getBoundingClientRect().top;
      const height = trackEl.offsetHeight - window.innerHeight;
      if (height <= 0) return 0;
      return Math.min(Math.max((window.scrollY - top) / height, 0), 1);
    }

    function getSolutionProgress() {
      if (!solutionPanel) return 0;
      const r = solutionPanel.getBoundingClientRect();
      const vh = window.innerHeight;
      const start = vh * 0.55;
      const end = -vh * 0.15;
      const raw = (start - r.top) / (start - end);
      return Math.min(Math.max(raw, 0), 1);
    }

    function drawContain(img: HTMLImageElement, alpha: number, offsetYpx: number) {
      if (!img?.naturalWidth) return;

      const { frameW, frameH, frameX, frameY } = getFrameBounds();
      const sw = img.naturalWidth;
      const sh = img.naturalHeight;
      const ratio = Math.min(frameW / sw, frameH / sh);
      const dw = sw * ratio;
      const dh = sh * ratio;
      const dx = frameX + (frameW - dw) / 2;
      const dy = frameY + (frameH - dh) / 2 + offsetYpx * dpr;

      ctx.globalAlpha = alpha;
      ctx.drawImage(img, 0, 0, sw, sh, dx, dy, dw, dh);
      ctx.globalAlpha = 1;
    }

    function renderArt(beat: number, solutionP: number) {
      const n = images.length;
      if (!n || loaded < n) {
        ctx.fillStyle = '#1a2744';
        ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
        return;
      }

      const imgBeat = Math.min(beat, IMAGE_COUNT - 1);
      const i0 = Math.floor(imgBeat);
      const i1 = Math.min(i0 + 1, IMAGE_COUNT - 1);
      const blend = imgBeat - i0;
      const lift = solutionP * canvasEl.height * 0.22;
      const imageAlpha = 1 - solutionP * 0.98;

      ctx.fillStyle = '#1a2744';
      ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);

      if (imageAlpha <= 0.02) return;

      drawContain(images[i0], imageAlpha * (1 - Math.min(blend, 1)), -lift);
      if (blend > 0.001 && i1 !== i0) {
        drawContain(images[i1], imageAlpha * blend, -lift);
      }
    }

    function syncBubbles(beat: number, solutionP: number) {
      captionPanels.forEach((panel, i) => {
        const bubble = panel.querySelector('.comic-bubble-wrap');
        if (!bubble) return;
        const active = Math.round(beat) === i && beat < CAPTION_COUNT;
        bubble.classList.toggle('visible', active);
      });

      if (solutionPanel) {
        const bubble = solutionPanel.querySelector('.comic-bubble-wrap');
        if (bubble) {
          bubble.classList.toggle('visible', solutionP > 0.06);
          (bubble as HTMLElement).style.setProperty('--solution-grow', solutionP.toFixed(3));
        }
      }

      canvasWrapEl.style.opacity = String(1 - solutionP * 0.95);
    }

    function tick() {
      const t = getScrollT();
      const beat = t * (panels.length - 1);
      const solutionP = getSolutionProgress();

      const delta = beat - smoothBeat;
      const abs = Math.abs(delta);
      const lerp = abs > 0.05 ? 0.14 : abs > 0.01 ? 0.09 : 0.06;
      smoothBeat += delta * lerp;
      smoothSolution += (solutionP - smoothSolution) * 0.12;

      renderArt(smoothBeat, smoothSolution);
      syncBubbles(smoothBeat, smoothSolution);

      if (progressBar) {
        progressBar.style.width = `${t * 100}%`;
        const trackRect = trackEl.getBoundingClientRect();
        const inTrack = trackRect.top < window.innerHeight && trackRect.bottom > 0;
        progressBar.classList.toggle('active', inTrack);
      }

      raf = requestAnimationFrame(tick);
    }

    function onImageLoad() {
      loaded += 1;
      if (loaded === PANEL_SRC.length) resizeCanvas();
    }

    PANEL_SRC.forEach((src, i) => {
      const img = new Image();
      img.decoding = 'async';
      img.onload = onImageLoad;
      img.onerror = onImageLoad;
      img.src = src;
      images[i] = img;
    });

    resizeCanvas();
    syncBubbles(0, 0);
    window.addEventListener('resize', resizeCanvas, { passive: true });
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, []);

  return (
    <>
      <div id="comic-progress" ref={progressRef} aria-hidden />

      <section className="comic-intro wrap" id="story">
        <p className="eyebrow reveal">Scroll comic · 6 panels</p>
        <h2 className="reveal serif">From flash to freedom.</h2>
        <p className="reveal" style={{ transitionDelay: '.05s' }}>
          One ticket. Six beats. Scroll to watch the story unfold — then see how Prosecuto fights back.
        </p>
        <span className="comic-scroll-hint reveal" style={{ transitionDelay: '.1s' }}>
          Scroll ↓
        </span>
      </section>

      <div className="comic-zone" id="comic-zone" ref={zoneRef}>
        <div className="comic-stage">
          <div id="comic-canvas-wrap" ref={canvasWrapRef} aria-hidden>
            <canvas id="comic-canvas" ref={canvasRef} />
            <div id="comic-vignette" />
            <div id="comic-halftone" />
          </div>

          <div id="comic-scroll-track" ref={trackRef}>
            <article className="comic-panel comic-panel--top" data-panel="0">
              <div className="comic-bubble-wrap comic-bubble-wrap--left">
                <div className="comic-bubble">
                  <p className="comic-chapter">Panel 01</p>
                  <p className="comic-quote">&quot;Yeah! I&apos;m flying!&quot;</p>
                  <p>Life in the fast lane — until the city has other plans.</p>
                </div>
              </div>
            </article>

            <article className="comic-panel comic-panel--bottom" data-panel="1">
              <div className="comic-bubble-wrap comic-bubble-wrap--right">
                <div className="comic-bubble">
                  <p className="comic-chapter">Panel 02</p>
                  <span className="comic-sfx">ZAP!</span>
                  <p>Red light camera. Owner liability. No demerits — but the fine still stings.</p>
                </div>
              </div>
            </article>

            <article className="comic-panel comic-panel--top" data-panel="2">
              <div className="comic-bubble-wrap comic-bubble-wrap--left">
                <div className="comic-bubble">
                  <p className="comic-chapter">Panel 03</p>
                  <p className="comic-quote">&quot;Oh no!&quot;</p>
                  <p>
                    <strong>$300 fine</strong> lands in your lap. HTA s.144 doesn&apos;t care who was driving — yet.
                  </p>
                </div>
              </div>
            </article>

            <article className="comic-panel comic-panel--bottom" data-panel="3">
              <div className="comic-bubble-wrap comic-bubble-wrap--right">
                <div className="comic-bubble">
                  <p className="comic-chapter">Panel 04</p>
                  <p className="comic-quote">&quot;Work your magic, app.&quot;</p>
                  <p>Prosecuto opens the playbook: grounds, scripts, and what to say in court.</p>
                </div>
              </div>
            </article>

            <article className="comic-panel comic-panel--top" data-panel="4">
              <div className="comic-bubble-wrap comic-bubble-wrap--left">
                <div className="comic-bubble">
                  <p className="comic-chapter">Panel 05</p>
                  <p className="comic-quote">&quot;This AI knows its stuff.&quot;</p>
                  <p>
                    <strong>Lawyer Mode</strong> builds your case. <strong>Judge Mode</strong> runs the full mock trial.
                  </p>
                </div>
              </div>
            </article>

            <article className="comic-panel comic-panel--image-only" data-panel="5" />

            <article className="comic-panel comic-panel--solution" data-panel="6">
              <div className="comic-bubble-wrap comic-bubble-wrap--solution comic-bubble-wrap--center">
                <div className="comic-bubble">
                  <p className="comic-chapter">The solution</p>
                  <h3 className="comic-title comic-title--fx">Victory!</h3>
                  <p className="comic-solution-lede">
                    <strong>Case dismissed.</strong> You walked in prepared — because you rehearsed every beat.
                  </p>
                  <p className="comic-solution-body">
                    Prosecuto coaches you through Early Resolution or a full mock trial — so you know exactly what to
                    say before you ever set foot in court.
                  </p>
                  <div className="comic-solution-actions">
                    <Link className="comic-solution-btn" href="/lawyer">
                      Prepare my case →
                    </Link>
                    <Link className="comic-solution-btn comic-solution-btn--ghost" href="/judge">
                      Run mock trial
                    </Link>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </>
  );
}
