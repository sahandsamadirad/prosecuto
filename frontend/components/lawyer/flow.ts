import type { DocKey } from './docs';

export type FlowStep = {
  text: string;
  suggest: string[];
  doc?: DocKey;
};

export const FLOW: FlowStep[] = [
  {
    text: "I'm Alex. I'll help you build a real defence for your red light camera ticket — plain language, your case only. To start: when were you issued the ticket, and which intersection was it?",
    suggest: ['March 3, 2026 — Hurontario & Eglinton', 'About two weeks ago', "I don't have the date in front of me"],
  },
  {
    text: 'Good. Now the question that decides everything: when the camera fired, were you driving — or is the car yours but someone else was behind the wheel?',
    suggest: ["It's my car, but my partner was driving", 'I was the driver', "I'd already sold the car"],
  },
  {
    text: "That's your strongest ground — owner was not the driver. A red light camera ticket is owner liability, so if we put the actual driver on the record with a sworn declaration, the charge against you becomes very hard to sustain. Here's the form we'll prepare.",
    doc: 'statdec',
    suggest: ['My partner will sign it', 'Will they get the ticket instead?', "What if they won't sign?"],
  },
  {
    text: "Next we make the Crown prove its case. I'll have you formally request full disclosure — the camera's operating and calibration records. You're entitled to it before trial, and gaps in it are a defence on their own. One more lever depends on timing.",
    doc: 'caselaw',
    suggest: ['My trial is 20 months out', "It's only a few months away", 'How do I request disclosure?'],
  },
  {
    text: "Then s.11(b) is live and I've flagged it. I've assembled everything into your preparation package — opening statement, the order you'll speak in, what to bring, and how to carry yourself. Read it, then I'd rehearse the whole thing in a mock trial before the real date.",
    doc: 'package',
    suggest: ['Open the package', 'Run a mock trial', 'Can you quiz me first?'],
  },
  {
    text: "Whenever you're ready, step into Judge Mode and we'll run the full hearing — Crown, clerk, and a Justice of the Peace — start to finish, then I'll review how you did. You can come back to me anytime to adjust the package.",
    suggest: ['Run mock trial', 'Stay and prepare more'],
  },
];

export const ROLE_META = {
  alex: { nm: 'Alex', rl: 'Lawyer', av: 'alex', glyph: 'A' },
  me: { nm: 'You', rl: 'Defendant', av: 'me', glyph: 'Y' },
} as const;
