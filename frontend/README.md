# Prosecuto Frontend (Next.js)

Next.js App Router app for the Prosecuto red light camera dispute experience.

## Routes

| Path | Page |
|------|------|
| `/` | Landing + scroll comic story |
| `/lawyer` | Lawyer Mode — Alex (case prep) |
| `/judge` | Judge Mode — mock trial |

## Development

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Build

```bash
npm run build
npm start
```

## Project structure

- `app/` — Next.js routes and layout
- `components/` — React UI (comic story, lawyer/judge apps, avatar)
- `lib/avatar-stage.ts` — Three.js GLB avatar (client-only)
- `public/assets/` — Comics images and avatar model
- `styles/` — Global CSS (design system, comic, meeting room)

## Legacy static files

The original HTML/JS files (`Prosecuto - Landing.html`, `Lawyer - Alex.html`, etc.) remain in this folder for reference. The Next.js app is the supported frontend going forward.
