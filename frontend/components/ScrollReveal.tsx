'use client';

import { useEffect } from 'react';

export default function ScrollReveal() {
  useEffect(() => {
    const reveals = Array.from(document.querySelectorAll('.reveal'));

    const revealInView = () => {
      const vh = window.innerHeight || document.documentElement.clientHeight;
      reveals.forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top < vh * 0.92 && r.bottom > 0) el.classList.add('in');
      });
    };

    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              e.target.classList.add('in');
              io.unobserve(e.target);
            }
          });
        },
        { threshold: 0.08, rootMargin: '0px 0px -6% 0px' }
      );
      reveals.forEach((el) => io.observe(el));
    }

    revealInView();
    window.addEventListener('scroll', revealInView, { passive: true });
    window.addEventListener('load', revealInView);
    const t = window.setTimeout(() => reveals.forEach((el) => el.classList.add('in')), 1400);

    return () => {
      window.removeEventListener('scroll', revealInView);
      window.removeEventListener('load', revealInView);
      window.clearTimeout(t);
    };
  }, []);

  return null;
}
