# Prosecuto — Frontend

Three self-contained HTML pages for the Prosecuto hackathon project. No build step — open `index.html` in any browser.

## Pages

| File | Description |
|------|-------------|
| `index.html` | Landing page — overview, defence grounds, dual CTA |
| `lawyer.html` | Lawyer Mode — interactive intake with Alex, document viewer |
| `judge.html` | Judge Mode — full Provincial Offences Court mock trial |

## Navigation

- Landing → **Prepare my case** → `lawyer.html`
- Landing → **Run mock trial** → `judge.html`
- Both app pages link back to `index.html`

## Assets

Drop your demo video at `assets/header.mp4` and uncomment the `<video>` tag in `index.html` (the slot is already wired with `data-src="assets/header.mp4"`).

For 3D face avatars, mount them into `.avatar-slot` on the left stage of `lawyer.html` and `judge.html`.

## Design system

- **Background:** `#F4F3EF` (Harvey warm-white) · **Ink:** `#1F1D1A`
- **Fonts:** Newsreader (serif) · Hanken Grotesk (body) · IBM Plex Mono (labels) — Google Fonts CDN
- **Framework:** React 18 + Babel standalone (CDN, no bundler) on the two app pages

## Wiring the LLM pipeline

The conversations in `lawyer.html` and `judge.html` are scripted demos. When ready:
- Replace the `FLOW` array in `lawyer.html` with live calls to your LLM
- Replace `charSpeak` triggers in `judge.html` with your TTS/ASR output
- The `send()` function in each page is the natural hook for your pipeline

Built for the NVIDIA Hackathon 2026.
