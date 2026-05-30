/**
 * Scroll-linked comic story — adapted from Astro scroll-landing
 * (fixed canvas art + tall panels + intersection reveals)
 */
(function () {
  const zone = document.getElementById('comic-zone');
  if (!zone) return;

  const canvas = document.getElementById('comic-canvas');
  const ctx = canvas.getContext('2d', { alpha: false });
  const progressBar = document.getElementById('comic-progress');
  const nav = document.getElementById('nav');
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
  let smoothT = 0;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  function resizeCanvas() {
    const w = zone.querySelector('#comic-canvas-wrap').clientWidth;
    const h = zone.querySelector('#comic-canvas-wrap').clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
  }

  function getZoneMetrics() {
    const rect = zone.getBoundingClientRect();
    const top = window.scrollY + rect.top;
    const height = zone.offsetHeight - window.innerHeight;
    return { top, height: Math.max(height, 1) };
  }

  function getScrollT() {
    const { top, height } = getZoneMetrics();
    const y = window.scrollY - top;
    return Math.min(Math.max(y / height, 0), 1);
  }

  function drawCover(img, alpha) {
    if (!img || !img.naturalWidth) return;
    const cw = canvas.width;
    const ch = canvas.height;
    const sw = img.naturalWidth;
    const sh = img.naturalHeight;
    const canvasRatio = cw / ch;
    const srcRatio = sw / sh;
    let cropX, cropY, cropW, cropH;
    if (srcRatio > canvasRatio) {
      cropH = sh;
      cropW = sh * canvasRatio;
      cropX = (sw - cropW) / 2;
      cropY = 0;
    } else {
      cropW = sw;
      cropH = sw / canvasRatio;
      cropX = 0;
      cropY = (sh - cropH) / 2;
    }
    ctx.globalAlpha = alpha;
    ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cw, ch);
    ctx.globalAlpha = 1;
  }

  function renderArt(t) {
    const n = images.length;
    if (!n || loaded < n) {
      ctx.fillStyle = '#0d0d0f';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return;
    }
    const pos = t * (n - 1);
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, n - 1);
    const blend = pos - i0;

    ctx.fillStyle = '#0d0d0f';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawCover(images[i0], 1);
    if (blend > 0.001 && i1 !== i0) {
      drawCover(images[i1], blend);
    }
  }

  function tick() {
    const t = getScrollT();
    const delta = t - smoothT;
    const abs = Math.abs(delta);
    const lerp = abs > 0.05 ? 0.14 : abs > 0.01 ? 0.09 : 0.06;
    smoothT += delta * lerp;

    renderArt(smoothT);

    if (progressBar) {
      progressBar.style.width = smoothT * 100 + '%';
      const inZone = t > 0.02 && t < 0.98;
      progressBar.classList.toggle('active', inZone);
    }

    if (nav) {
      const rect = zone.getBoundingClientRect();
      const inside = rect.top < 80 && rect.bottom > 80;
      nav.classList.toggle('comic-active', inside);
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
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
  );
  bubbles.forEach((b) => io.observe(b));

  const first = zone.querySelector('.comic-bubble-wrap');
  if (first) first.classList.add('visible');

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas, { passive: true });
  requestAnimationFrame(tick);
})();
