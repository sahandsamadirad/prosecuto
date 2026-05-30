'use client';

import Link from 'next/link';
import { useEffect } from 'react';

export default function LandingNav() {
  useEffect(() => {
    const nav = document.getElementById('nav');
    const comicZone = document.getElementById('comic-zone');
    if (!nav) return undefined;

    const onScroll = () => {
      const inComic = comicZone
        ? (() => {
            const r = comicZone.getBoundingClientRect();
            return r.top < 72 && r.bottom > 72;
          })()
        : false;
      nav.classList.toggle('solid', window.scrollY > 8);
      nav.classList.toggle('comic-active', !!inComic);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <nav className="nav" id="nav">
      <Link className="brand" href="#top">
        <span className="mark" />
        Prosecuto
      </Link>
      <div className="nav-links">
        <a href="#story">Story</a>
      </div>
      <div className="nav-cta">
        <Link className="btn btn-ghost" href="/lawyer">
          Prepare my case
        </Link>
      </div>
    </nav>
  );
}
