/**
 * Scroll-linked comic story
 * Panels 0–4: images 1–5 + captions
 * Panel 5: image 6 only (no caption)
 * Panel 6: image exits upward, blue solution card expands
 */
(function () {
  const zone = document.getElementById('comic-zone');
  if (!zone) return;

  const canvas = document.getElementById('comic-canvas');
  const canvasWrap = document.getElementById('comic-canvas-wrap');
  const ctx = canvas.getContext('2d', { alpha: false });
  const progressBar = document.getElementById('comic-progress');
  const track = document.getElementById('comic-scroll-track');
  const panels = track ? [...track.querySelectorAll('.comic-panel')] : [];
  const solutionPanel = track ? track.querySelector('.comic-panel--solution') : null;

  const PANEL_SRC = [
    'assets/comics/1.jpg',
    'assets/comics/2.jpg',
    'assets/comics/3.jpg',
    'assets/comics/4.jpg',
    'assets/comics/5.png',
    'assets/comics/6.png',
  ];

  const IMAGE_COUNT = PANEL_SRC.length;
  const CAPTION_COUNT = 5;
  const captionPanels = panels.slice(0, CAPTION_COUNT);

  const images = [];
  let loaded = 0;
  let smoothBeat = 0;
  let smoothSolution = 0;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  /** Max fraction of viewport for art — equal ~19% margin on every edge */
  const FRAME_SCALE = 0.62;

  function resizeCanvas() {
    if (!canvasWrap) return;
    const w = canvasWrap.clientWidth;
    const h = canvasWrap.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
  }

  function getFrameBounds() {
    const cw = canvas.width;
    const ch = canvas.height;
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
    if (!track) return 0;
    const top = window.scrollY + track.getBoundingClientRect().top;
    const height = track.offsetHeight - window.innerHeight;
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

  /** Fit inside a centered frame — equal top/bottom and left/right margins */
  function drawContain(img, alpha, offsetYpx) {
    if (!img || !img.naturalWidth) return;

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

  function renderArt(beat, solutionP) {
    const n = images.length;
    if (!n || loaded < n) {
      ctx.fillStyle = '#1a2744';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const imgBeat = Math.min(beat, IMAGE_COUNT - 1);
    const i0 = Math.floor(imgBeat);
    const i1 = Math.min(i0 + 1, IMAGE_COUNT - 1);
    const blend = imgBeat - i0;
    const lift = solutionP * canvas.height * 0.22;
    const imageAlpha = 1 - solutionP * 0.98;

    ctx.fillStyle = '#1a2744';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    if (imageAlpha <= 0.02) return;

    drawContain(images[i0], imageAlpha * (1 - Math.min(blend, 1)), -lift);
    if (blend > 0.001 && i1 !== i0) {
      drawContain(images[i1], imageAlpha * blend, -lift);
    }
  }

  function syncBubbles(beat, solutionP) {
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
        bubble.style.setProperty('--solution-grow', solutionP.toFixed(3));
      }
    }

    if (canvasWrap) {
      canvasWrap.style.opacity = String(1 - solutionP * 0.95);
    }
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
      progressBar.style.width = t * 100 + '%';
      const trackRect = track.getBoundingClientRect();
      const inTrack = trackRect.top < window.innerHeight && trackRect.bottom > 0;
      progressBar.classList.toggle('active', inTrack);
    }

    requestAnimationFrame(tick);
  }

  function onImageLoad() {
    loaded++;
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
  requestAnimationFrame(tick);
})();
