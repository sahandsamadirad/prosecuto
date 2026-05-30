import type { Metadata } from 'next';
import { Bangers, Comic_Neue } from 'next/font/google';
import './globals.css';

const bangers = Bangers({
  weight: '400',
  subsets: ['latin'],
  variable: '--font-bangers',
  display: 'swap',
});

const comicNeue = Comic_Neue({
  weight: ['400', '700'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-comic-neue',
  display: 'swap',
});

export const metadata: Metadata = {
  title: {
    default: 'Prosecuto — Dispute your red light camera ticket',
    template: '%s · Prosecuto',
  },
  description:
    'Prosecuto prepares Ontario citizens to dispute a red light camera ticket — coaching you through Early Resolution and rehearsing the full trial.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${bangers.variable} ${comicNeue.variable}`}>
      <body>{children}</body>
    </html>
  );
}
