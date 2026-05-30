import type { ReactNode } from 'react';

export type DocKey = 'statdec' | 'caselaw' | 'package';

export const DOCS: Record<
  DocKey,
  { title: string; sub: string; render: () => ReactNode }
> = {
  statdec: {
    title: 'Statutory Declaration',
    sub: 'Ground 1 · Owner was not the driver',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Form · Ontario</span>
          <span>Prov. Offences Act</span>
        </div>
        <h2>Statutory Declaration</h2>
        <div className="sec-no">Declaration of the Vehicle Owner</div>
        <p>
          I, <span className="fill">[owner full name]</span>, of the City of{' '}
          <span className="fill">[city]</span>, in the Province of Ontario, do solemnly declare that:
        </p>
        <p>
          1. I am the registered owner of the motor vehicle bearing Ontario licence plate{' '}
          <span className="fill">[plate]</span>.
        </p>
        <p>
          2. On <span className="fill">[offence date]</span>, at the intersection of{' '}
          <span className="fill">[intersection]</span>, I was <b>not</b> the driver of the said vehicle.
        </p>
        <p>
          3. The driver at the relevant time was <span className="fill">[driver name]</span>, who has knowledge of
          these facts.
        </p>
        <p>
          And I make this solemn declaration conscientiously believing it to be true, and knowing that it is of the
          same force and effect as if made under oath.
        </p>
        <div className="sig-row">
          <div className="sig">Declarant signature</div>
          <div className="sig">Commissioner for taking affidavits</div>
        </div>
      </div>
    ),
  },
  caselaw: {
    title: 'R. v. Jordan, 2016 SCC 27',
    sub: 'Case law · s.11(b) Charter — delay',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Supreme Court of Canada</span>
          <span>2016 SCC 27</span>
        </div>
        <h2>R. v. Jordan</h2>
        <div className="sec-no">Right to be tried within a reasonable time</div>
        <p>
          The Supreme Court set a <b>presumptive ceiling</b> beyond which delay is considered unreasonable under
          s.11(b) of the Charter. For matters in provincial court, that ceiling is <b>18 months</b> from the charge to
          the actual or anticipated end of trial.
        </p>
        <p className="cite">
          “…a presumptive ceiling of 18 months for cases tried in the provincial court. Delay beyond this ceiling is
          presumptively unreasonable.”
        </p>
        <p style={{ marginTop: '18px' }}>
          <b>Why it matters for you:</b> if your trial date falls more than 18 months after the date on your
          Certificate of Offence, this is a live ground to have the charge stayed. We will calculate this precisely
          once we confirm both dates.
        </p>
        <p style={{ color: 'var(--muted)', fontSize: '14px' }}>
          Verify the current state of the law with a paralegal — ceilings and deductions have nuance.
        </p>
      </div>
    ),
  },
  package: {
    title: 'Your Preparation Package',
    sub: 'Generated for your case',
    render: () => (
      <div className="legal-doc">
        <div className="lh">
          <span>Prosecuto · Lawyer Mode</span>
          <span>Draft v1</span>
        </div>
        <h2>Preparation Package</h2>
        <div className="sec-no">Dispute path · Both — Early Resolution, then Trial</div>
        <p
          style={{
            fontFamily: 'var(--mono)',
            fontSize: '12px',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--muted-2)',
          }}
        >
          [ Opening statement ]
        </p>
        <p>
          “Good morning, Your Worship. My name is <span className="fill">[name]</span>. I am the registered owner of
          the vehicle, but I was not its driver on the date in question, and I&apos;ll be relying on a statutory
          declaration to that effect.”
        </p>
        <p
          style={{
            fontFamily: 'var(--mono)',
            fontSize: '12px',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--muted-2)',
            marginTop: '24px',
          }}
        >
          [ Defence script — order of play ]
        </p>
        <p>
          1. Confirm your identity and ownership.
          <br />
          2. Tender the statutory declaration naming the driver.
          <br />
          3. Request the camera operating &amp; calibration certificate in disclosure.
          <br />
          4. If the trial date is &gt; 18 months out, raise s.11(b).
        </p>
        <p
          style={{
            fontFamily: 'var(--mono)',
            fontSize: '12px',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--muted-2)',
            marginTop: '24px',
          }}
        >
          [ Bring to court ]
        </p>
        <p>
          — Signed statutory declaration
          <br />— A copy of the Certificate of Offence
          <br />— Any disclosure the Crown provided
        </p>
        <p
          style={{
            fontFamily: 'var(--mono)',
            fontSize: '12px',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--muted-2)',
            marginTop: '24px',
          }}
        >
          [ Delivery ]
        </p>
        <p>
          Address the bench as “Your Worship.” Speak slowly. Don&apos;t argue facts that aren&apos;t in dispute.
          Concede nothing about who was driving beyond the declaration.
        </p>
      </div>
    ),
  },
};
