import type { ReactNode } from 'react';

export type CharKey = 'clerk' | 'judge' | 'crown' | 'me' | 'prosecuto';
export type JudgeDocKey = 'certificate' | 'photo' | 'camcert';

export const CHARS: Record<
  CharKey,
  { nm: string; rl: string; av: string; glyph: string; color: string }
> = {
  clerk: { nm: 'Court Clerk', rl: 'Clerk', av: 'clerk', glyph: 'K', color: '#4a4533' },
  judge: { nm: 'Justice of the Peace', rl: 'The Bench', av: 'judge', glyph: 'J', color: '#25324a' },
  crown: { nm: 'Crown Prosecutor', rl: 'Crown', av: 'crown', glyph: 'P', color: '#6f2c2c' },
  me: { nm: 'You', rl: 'Defendant', av: 'me', glyph: 'Y', color: '#1E6FD9' },
  prosecuto: { nm: 'Prosecuto', rl: 'Review', av: 'alex', glyph: '✦', color: '#1E6FD9' },
};

export const DOCS: Record<
  JudgeDocKey,
  { title: string; sub: string; render: () => ReactNode }
> = {
  certificate: {
    title: 'Certificate of Offence',
    sub: 'Exhibit 1 · tendered by the Crown',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Provincial Offences Act</span>
          <span>Exhibit 1</span>
        </div>
        <h2>Certificate of Offence</h2>
        <div className="sec-no">Red light camera · HTA s.144</div>
        <p>
          Plate number: <span className="fill">[plate]</span>
          <br />
          Date of offence: <span className="fill">[date]</span>
          <br />
          Location: <span className="fill">[intersection]</span>
          <br />
          Issuing officer / badge no.: <span className="fill">[badge]</span>
        </p>
        <p>
          The provincial offences officer certifies that they have reasonable and probable grounds to believe, and do
          believe, that the offence was committed.
        </p>
        <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
          Defence note: examine for defects — a missing badge number, wrong date, or mismatched plate can defeat the
          certificate (Ground 6).
        </p>
      </div>
    ),
  },
  photo: {
    title: 'Photograph — camera capture',
    sub: 'Exhibit 2 · tendered by the Crown',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Camera system</span>
          <span>Exhibit 2</span>
        </div>
        <h2>Photographic Evidence</h2>
        <div className="sec-no">Intersection capture · two frames</div>
        <div
          className="placeholder-stripes"
          style={{
            aspectRatio: '4/3',
            borderRadius: '8px',
            border: '1px solid var(--line-2)',
            display: 'grid',
            placeItems: 'center',
            marginBottom: '16px',
          }}
        >
          <code style={{ fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted)' }}>
            [ camera capture — intersection &amp; plate ]
          </code>
        </div>
        <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
          Defence note: does the image clearly identify the plate and the driver? Owner liability means the photo need
          not show the driver&apos;s face — but plate clarity is fair game (Ground 4).
        </p>
      </div>
    ),
  },
  camcert: {
    title: 'Camera Operating Certificate',
    sub: 'Exhibit 3 · tendered by the Crown',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Equipment record</span>
          <span>Exhibit 3</span>
        </div>
        <h2>Camera Operating Certificate</h2>
        <div className="sec-no">Calibration &amp; maintenance</div>
        <p>
          This certifies that the red light camera system at the location was tested and operating accurately at the
          material time.
        </p>
        <p>
          Last calibration: <span className="fill">[date]</span>
          <br />
          Amber phase duration: <span className="fill">[seconds]</span>
          <br />
          Maintenance on record: <span className="fill">[yes / no]</span>
        </p>
        <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
          Defence note: request the full calibration and maintenance records in disclosure. Gaps support Ground 2
          (malfunction); a short amber phase supports Ground 5.
        </p>
      </div>
    ),
  },
};

export type Phase = {
  rail: string;
  mode: 'auto' | 'user' | 'verdict';
  who?: CharKey;
  text?: string;
  docs?: JudgeDocKey[];
  cue?: { who: CharKey; text: string };
  suggest?: string[];
  reply?: { who: CharKey; text: string };
};

export const PHASES: Phase[] = [
  {
    rail: 'Call to order',
    who: 'clerk',
    mode: 'auto',
    text: 'All rise. The Ontario Court of Justice, Provincial Offences Court, is now in session. You may be seated. We are here on the matter of the City versus the defendant — one count under the Highway Traffic Act, section 144, red light camera.',
  },
  {
    rail: 'Affirmation',
    mode: 'user',
    cue: {
      who: 'clerk',
      text: 'Do you affirm that the evidence you give to this court will be the truth, the whole truth, and nothing but the truth?',
    },
    suggest: ['I do solemnly affirm.', 'I affirm.'],
  },
  {
    rail: 'Court opens',
    who: 'judge',
    mode: 'auto',
    text: 'Thank you. I am the Justice of the Peace hearing this matter. The standard of proof is beyond a reasonable doubt, and the burden rests with the Crown throughout. Madam Prosecutor, you may open.',
  },
  {
    rail: 'Crown opening',
    who: 'crown',
    mode: 'auto',
    text: 'Thank you, Your Worship. The Crown will show that on the date in question, the vehicle registered to the defendant entered the intersection against a red signal, captured by an approved red light camera system. The evidence is a certificate of offence, a photograph, and the camera operating certificate.',
  },
  {
    rail: 'Defence opening',
    mode: 'user',
    cue: { who: 'judge', text: 'The defence may now make its opening statement.' },
    suggest: [
      "I'm the registered owner, but I was not the driver.",
      "I'll rely on a statutory declaration naming the driver.",
      'I dispute that the plate is clearly identified.',
    ],
  },
  {
    rail: "Crown's case",
    who: 'crown',
    mode: 'auto',
    text: "The Crown tenders three exhibits, Your Worship: the Certificate of Offence as Exhibit 1, the photographic capture as Exhibit 2, and the Camera Operating Certificate as Exhibit 3. The Crown's case rests on the certificate and the operating record.",
    docs: ['certificate', 'photo', 'camcert'],
  },
  {
    rail: 'Cross Crown',
    mode: 'user',
    cue: { who: 'judge', text: "You may cross-examine on the Crown's evidence." },
    suggest: [
      "Was the camera's calibration record disclosed to me?",
      'Does the photograph clearly identify the driver?',
      'When was the equipment last serviced?',
    ],
    reply: {
      who: 'crown',
      text: 'The operating certificate is tendered, Your Worship; the full underlying calibration log was not included in the disclosure package. As to the driver — this is an owner-liability offence; the Crown does not allege a specific driver.',
    },
  },
  {
    rail: 'Defence case',
    mode: 'user',
    cue: { who: 'judge', text: 'The defence may now present its case.' },
    suggest: [
      'I tender a statutory declaration — I was not the driver.',
      'The Crown failed to disclose the calibration records.',
      'There was no proper advance signage at the intersection.',
    ],
  },
  {
    rail: 'Cross defence',
    mode: 'user',
    cue: {
      who: 'crown',
      text: 'Just one question. You acknowledge that you are the registered owner of the vehicle, correct?',
    },
    suggest: [
      'Yes — but ownership is not driving, and a declaration names the driver.',
      'I own it, yes. I was not behind the wheel.',
    ],
    reply: { who: 'crown', text: 'No further questions, Your Worship.' },
  },
  {
    rail: 'Crown closing',
    who: 'crown',
    mode: 'auto',
    text: "In closing, the Crown's evidence establishes the offence on an owner-liability basis. The Crown acknowledges, however, that the full calibration log was not disclosed. The Crown submits the certificate alone is sufficient and leaves the matter to Your Worship.",
  },
  {
    rail: 'Defence closing',
    mode: 'user',
    cue: { who: 'judge', text: 'And finally, the defence may close.' },
    suggest: [
      "The Crown's own admission of non-disclosure leaves reasonable doubt.",
      'The driver was never established, and the declaration stands unchallenged.',
      'I respectfully ask that the charge be dismissed.',
    ],
  },
  {
    rail: 'Verdict',
    who: 'judge',
    mode: 'verdict',
    text: "I've heard both sides. Having considered the evidence and the Crown's admission regarding disclosure, I find as follows.",
  },
];

export const VERDICT = {
  result: 'NOT GUILTY',
  line: 'The Crown bears the burden beyond a reasonable doubt. The defence tendered an unchallenged statutory declaration, and the Crown conceded the calibration log was not disclosed. On this record, the court is left with a reasonable doubt. The charge is dismissed.',
  feedback: [
    {
      k: 'Strong',
      cls: 'good' as const,
      t: 'You raised the disclosure gap early and made the Crown concede it on the record — that\'s what created the doubt.',
    },
    {
      k: 'Strong',
      cls: 'good' as const,
      t: "Tendering the statutory declaration cleanly, without over-explaining, kept the driver's identity unproven.",
    },
    {
      k: 'Fix',
      cls: 'fix' as const,
      t: 'On cross, you volunteered ownership a little fast. Answer only what\'s asked — "Yes" was enough before adding the qualifier.',
    },
    {
      k: 'Fix',
      cls: 'fix' as const,
      t: 'You addressed the bench as "Your Honour" once. In Provincial Offences Court it\'s "Your Worship." Small thing, but it signals preparation.',
    },
  ],
};
