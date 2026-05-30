/**
 * Scroll-linked comic story — panel-index sync (per beat, not zone fraction)
 */
(function () {
  const zone = document.getElementById('comic-zone');
  if (!zone) return;

  const canvas = document.getElementById('comic-canvas');
  const ctx = canvas.getContext('2d', { alpha: false });
  const progressBar = document.getElementById('comic-progress');
  const track = document.getElementById('comic-scroll-track');
  const panels = track ? [...track.querySelectorAll('.comic-panel')] : [];
  const bubbles = zone.querySelectorAll('.comic-bubble-wrap');

  const PANEL_SRC = [
    'assets/comics/1.jpg',
    'assets/comics/2.jpg',
    'assets/comics/3.jpg',
    'assets/comics/4.jpg',
    'assets/comics/5.png',
    'assets/comics/6.png',
  ];

  const images = [];
  let loaded = 0;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const ART_SCALE = 0.58;
  const MARKER_RATIO = 0.42;

  function resizeCanvas() {
    const wrap = zone.querySelector('#comic-canvas-wrap');
    if (!wrap) return;
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
  }

  /** Which panel is at the viewport marker, and blend to the next */
  function getPanelState() {
    if (!panels.length) return { index: 0, blend: 0 };

    const marker = window.innerHeight * MARKER_RATIO;
    let index = 0;
    let blend = 0;

    for (let i = 0; i < panels.length; i++) {
      const r = panels[i].getBoundingClientRect();

      if (r.top <= marker && r.bottom > marker) {
        index = i;
        const inner = (marker - r.top) / Math.max(r.height, 1);
        blend = Math.min(1, Math.max(0, (inner - 0.35) / 0.35));
        return { index, blend };
      }

      if (i < panels.length - 1) {
        const next = panels[i + 1].getBoundingClientRect();
        if (r.bottom <= marker && next.top > marker) {
          index = i;
          const gap = next.top - r.bottom;
          blend = gap > 0 ? Math.min(1, (marker - r.bottom) / gap) : 1;
          return { index, blend };
        }
      }
    }

    const last = panels[panels.length - 1].getBoundingClientRect();
    if (last.top <= marker) {
      return { index: panels.length - 1, blend: 0 };
    }
    return { index: 0, blend: 0 };
  }

  function drawContain(img, alpha) {
    if (!img || !img.naturalWidth) return;
    const cw = canvas.width;
    const ch = canvas.height;
    const sw = img.naturalWidth;
    const sh = img.naturalHeight;
    const maxW = cw * ART_SCALE;
    const maxH = ch * ART_SCALE;
    const ratio = Math.min(maxW / sw, maxH / sh);
    const dw = sw * ratio;
    const dh = sh * ratio;
    const dx = (cw - dw) / 2;
    const dy = (ch - dh) / 2;
    ctx.globalAlpha = alpha;
    ctx.drawImage(img, 0, 0, sw, sh, dx, dy, dw, dh);
    ctx.globalAlpha = 1;
  }

  function renderArt(index, blend) {
    const n = images.length;
    if (!n || loaded < n) {
      ctx.fillStyle = '#1a2744';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const i0 = Math.max(0, Math.min(index, n - 1));
    const i1 = Math.min(i0 + 1, n - 1);

    ctx.fillStyle = '#1a2744';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawContain(images[i0], 1);
    if (blend > 0.02 && i1 !== i0) {
      drawContain(images[i1], blend);
    }
  }

  function tick() {
    const { index, blend } = getPanelState();
    renderArt(index, blend);

    if (progressBar && panels.length > 1) {
      const progress = (index + blend) / (panels.length - 1);
      progressBar.style.width = progress * 100 + '%';
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

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('visible');
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.06, rootMargin: '0px 0px -5% 0px' }
  );
  bubbles.forEach((b) => io.observe(b));

  const first = zone.querySelector('.comic-bubble-wrap');
  if (first) first.classList.add('visible');

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas, { passive: true });
  requestAnimationFrame(tick);
})();
