'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { CHARS, DOCS, PHASES, VERDICT, type CharKey, type JudgeDocKey } from './data';

const AvatarMount = dynamic(() => import('@/components/AvatarMount'), { ssr: false });

type Message = {
  role: CharKey;
  text: string | null;
  doc: JudgeDocKey | null;
};

export default function JudgeApp() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [cur, setCur] = useState(-1);
  const [suggest, setSuggest] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [active, setActive] = useState<CharKey>('clerk');
  const [caption, setCaption] = useState<{ who: CharKey; text: string; show: boolean }>({
    who: 'clerk',
    text: '',
    show: false,
  });
  const [thinking, setThinking] = useState(false);
  const [tab, setTab] = useState<'chat' | 'docs'>('chat');
  const [openDoc, setOpenDoc] = useState<JudgeDocKey | null>(null);
  const [mic, setMic] = useState(false);
  const [ended, setEnded] = useState(false);
  const tRef = useRef<HTMLDivElement>(null);
  const capTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const sharedDocs = messages.filter((m) => m.doc).map((m) => m.doc!);

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => {
      const el = tRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const speak = useCallback((who: CharKey, text: string, after?: () => void) => {
    if (capTimer.current) clearInterval(capTimer.current);
    setActive(who);
    setSpeaking(true);
    setCaption({ who, text: '', show: true });
    const words = text.split(' ');
    let i = 0;
    capTimer.current = setInterval(() => {
      i += 1;
      setCaption({ who, text: words.slice(0, i).join(' '), show: true });
      if (i >= words.length) {
        if (capTimer.current) clearInterval(capTimer.current);
        setTimeout(() => {
          setSpeaking(false);
          after?.();
        }, 650);
      }
    }, 48);
  }, []);

  const charSpeak = useCallback(
    (who: CharKey, text: string, docs: JudgeDocKey[] | undefined, after?: () => void) => {
      setSuggest([]);
      setThinking(true);
      scrollDown();
      setTimeout(() => {
        setThinking(false);
        setMessages((m) => [...m, { role: who, text, doc: null }]);
        if (docs) {
          docs.forEach((d, k) => {
            setTimeout(() => {
              setMessages((m) => [...m, { role: who, text: null, doc: d }]);
              scrollDown();
            }, 500 + k * 450);
          });
        }
        speak(who, text, after);
        scrollDown();
      }, 800);
    },
    [speak, scrollDown]
  );

  const arrive = useCallback(
    (i: number) => {
      const p = PHASES[i];
      if (!p) return;
      setCur(i);
      if (p.mode === 'auto' && p.who && p.text) {
        charSpeak(p.who, p.text, p.docs, () => setTimeout(() => arrive(i + 1), 700));
      } else if (p.mode === 'verdict' && p.who && p.text) {
        charSpeak(p.who, p.text, undefined, () => setTimeout(() => setEnded(true), 600));
      } else if (p.mode === 'user' && p.cue) {
        charSpeak(p.cue.who, p.cue.text, undefined, () => setSuggest(p.suggest || []));
      }
    },
    [charSpeak]
  );

  useEffect(() => {
    const t = setTimeout(() => arrive(0), 700);
    return () => clearTimeout(t);
  }, [arrive]);

  useEffect(scrollDown, [messages, thinking, ended]);

  const send = (text?: string) => {
    const val = (text ?? input).trim();
    if (!val || thinking) return;
    const p = PHASES[cur];
    if (!p || p.mode !== 'user') return;
    if (capTimer.current) clearInterval(capTimer.current);
    setSpeaking(false);
    setMessages((m) => [...m, { role: 'me', text: val, doc: null }]);
    setInput('');
    setSuggest([]);
    setMic(false);
    setTimeout(() => {
      if (p.reply) {
        charSpeak(p.reply.who, p.reply.text, undefined, () => setTimeout(() => arrive(cur + 1), 600));
      } else {
        arrive(cur + 1);
      }
    }, 550);
  };

  const restart = () => {
    setMessages([]);
    setCur(-1);
    setSuggest([]);
    setEnded(false);
    setCaption({ who: 'clerk', text: '', show: false });
    setActive('clerk');
    setTimeout(() => arrive(0), 500);
  };

  const aMeta = CHARS[active];

  return (
    <div className="room">
      <div className={'stage' + (speaking ? ' speaking' : '')}>
        <div className="stage-top">
          <Link className="back-link" href="/">
            ← Prosecuto
          </Link>
          <span className="mode-pill">Judge Mode · Mock trial</span>
        </div>

        <div className="avatar-slot">
          <AvatarMount speaking={speaking} />
          <div className="avatar-info">
            <div className="avatar-fallback">
              <div className="ring" style={{ borderColor: `${aMeta.color}55` }}>
                <span className="avatar-glyph" style={{ color: aMeta.color }}>
                  {aMeta.glyph}
                </span>
              </div>
            </div>
            <div className="who-name serif">{aMeta.nm}</div>
            <div className="who-role">{aMeta.rl} · now speaking</div>
          </div>
        </div>

        <div className="caption">
          <div className={'caption-inner' + (caption.show ? ' show' : '')}>
            <span className="spk">
              {CHARS[caption.who]?.nm}
              <span className="wave">
                <i />
                <i />
                <i />
                <i />
                <i />
              </span>
            </span>
            {caption.text || '…'}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div>
            <h1 className="serif">Provincial Offences Court</h1>
            <div className="sub">City v. Defendant · HTA s.144</div>
          </div>
          <div className="head-tabs">
            <button className={tab === 'chat' ? 'active' : ''} type="button" onClick={() => setTab('chat')}>
              Transcript
            </button>
            <button className={tab === 'docs' ? 'active' : ''} type="button" onClick={() => setTab('docs')}>
              Evidence <span className="badge">{sharedDocs.length}</span>
            </button>
          </div>
        </div>

        <div className="rail">
          {PHASES.map((p, i) => (
            <div
              key={i}
              className={'ph' + (i === cur && !ended ? ' cur' : '') + (i < cur || ended ? ' done' : '')}
            >
              <span className="dot">{i < cur || ended ? '✓' : i + 1}</span>
              <span className="lb">{p.rail}</span>
            </div>
          ))}
        </div>

        {tab === 'chat' ? (
          <div className="transcript" ref={tRef}>
            {messages.map((m, i) => {
              const meta = CHARS[m.role];
              if (m.doc) {
                return (
                  <div key={i} className="turn" style={{ maxWidth: '78%' }}>
                    <div className="doc-card" style={{ marginTop: 0 }} onClick={() => setOpenDoc(m.doc)} role="presentation">
                      <div className="dc-top">
                        <div className="dc-ico" />
                        <div>
                          <div className="dc-t">{DOCS[m.doc].title}</div>
                          <div className="dc-s">{DOCS[m.doc].sub}</div>
                        </div>
                        <div className="dc-open">Open →</div>
                      </div>
                    </div>
                  </div>
                );
              }
              return (
                <div key={i} className={'turn' + (m.role === 'me' ? ' me' : '')}>
                  <div className="meta">
                    <span className={'av ' + meta.av}>{meta.glyph}</span>
                    <span className="nm">{meta.nm}</span>
                    <span className="rl">{meta.rl}</span>
                  </div>
                  <div className="body">{m.text}</div>
                </div>
              );
            })}
            {thinking && (
              <div className="turn">
                <div className="meta">
                  <span className={'av ' + CHARS[active].av}>{CHARS[active].glyph}</span>
                  <span className="nm">{CHARS[active].nm}</span>
                </div>
                <div className="body">
                  <span className="thinking">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </div>
            )}

            {ended && (
              <div className="verdict-wrap">
                <div className="verdict-banner">
                  <div className="vb-top">
                    <div className="vlabel">The court finds the defendant</div>
                    <div className="vresult serif">{VERDICT.result}</div>
                  </div>
                  <div className="vline">{VERDICT.line}</div>
                </div>
                <div className="feedback-card">
                  <div className="fh">
                    <span className="av">✦</span>
                    <span className="nm">Prosecuto</span>
                    <span className="rl">Breaking character · performance review</span>
                  </div>
                  {VERDICT.feedback.map((f, i) => (
                    <div key={i} className={'fb-item ' + f.cls}>
                      <span className="k">{f.k}</span>
                      <span>{f.t}</span>
                    </div>
                  ))}
                  <div className="verdict-actions">
                    <button className="btn btn-primary" type="button" onClick={restart}>
                      Run it again
                    </button>
                    <Link className="btn btn-ghost" href="/lawyer">
                      Back to prep with Alex
                    </Link>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="transcript" ref={tRef}>
            {sharedDocs.length === 0 && (
              <p style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: '13px' }}>
                No exhibits tendered yet.
              </p>
            )}
            {sharedDocs.map((d, i) => (
              <div
                key={i}
                className="doc-card"
                style={{ marginBottom: '14px' }}
                onClick={() => setOpenDoc(d)}
                role="presentation"
              >
                <div className="dc-top">
                  <div className="dc-ico" />
                  <div>
                    <div className="dc-t">{DOCS[d].title}</div>
                    <div className="dc-s">{DOCS[d].sub}</div>
                  </div>
                  <div className="dc-open">Open →</div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="composer">
          {suggest.length > 0 && (
            <div className="suggest">
              {suggest.map((s, i) => (
                <button key={i} className="chip" type="button" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
          <div className="input-row">
            <textarea
              rows={1}
              placeholder={
                ended
                  ? 'The trial has concluded.'
                  : PHASES[cur] && PHASES[cur].mode === 'user'
                    ? 'Address the court… (it\'s your turn)'
                    : 'Listening to the court…'
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              className={'icon-btn mic' + (mic ? ' live' : '')}
              type="button"
              onClick={() => setMic((v) => !v)}
              title="Voice input"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
              </svg>
            </button>
            <button className="icon-btn send-btn" type="button" disabled={!input.trim()} onClick={() => send()} title="Send">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>

        <div className={'docview' + (openDoc ? ' open' : '')}>
          <div className="scrim" onClick={() => setOpenDoc(null)} role="presentation" />
          <div className="sheet">
            {openDoc && (
              <>
                <div className="sheet-head">
                  <div>
                    <div className="st">{DOCS[openDoc].title}</div>
                    <div className="ss">{DOCS[openDoc].sub}</div>
                  </div>
                  <button className="icon-btn" type="button" onClick={() => setOpenDoc(null)} title="Close">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
                <div className="sheet-body">{DOCS[openDoc].render()}</div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
