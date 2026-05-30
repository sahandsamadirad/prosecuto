import Link from 'next/link';
import ComicStory from '@/components/ComicStory';
import LandingNav from '@/components/LandingNav';
import ScrollReveal from '@/components/ScrollReveal';

export default function HomePage() {
  return (
    <>
      <LandingNav />
      <ScrollReveal />

      <main id="top">
        <section className="hero wrap">
          <div className="hero-grid">
            <div>
              <h1 className="reveal">
                Fight your ticket. <em>Without a lawyer.</em>
              </h1>
              <p className="hero-sub reveal" style={{ transitionDelay: '.05s' }}>
                Prosecuto prepares Ontario citizens to dispute a red light camera ticket — coaching you through Early
                Resolution and rehearsing the full trial against an AI Justice of the Peace before you ever set foot in
                court.
              </p>
              <div className="hero-actions reveal" style={{ transitionDelay: '.1s' }}>
                <Link className="btn btn-primary" href="/judge">
                  Run mock trial <span className="arrow">→</span>
                </Link>
                <a className="btn btn-ghost" href="#story">
                  Read the story
                </a>
              </div>
            </div>
          </div>
        </section>

        <ComicStory />
      </main>
    </>
  );
}
