'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DOCS, type DocKey } from './docs';
import { FLOW, ROLE_META } from './flow';

const AvatarMount = dynamic(() => import('@/components/AvatarMount'), { ssr: false });

type Message = {
  role: 'alex' | 'me';
  text: string;
  doc: DocKey | null;
};

export default function LawyerApp() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [step, setStep] = useState(-1);
  const [suggest, setSuggest] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState({ text: '', show: false });
  const [thinking, setThinking] = useState(false);
  const [tab, setTab] = useState<'chat' | 'docs'>('chat');
  const [openDoc, setOpenDoc] = useState<DocKey | null>(null);
  const [mic, setMic] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const captionTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const sharedDocs = messages.filter((m) => m.doc).map((m) => m.doc!);

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => {
      const el = transcriptRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const speak = useCallback((text: string) => {
    if (captionTimer.current) clearInterval(captionTimer.current);
    setSpeaking(true);
    setCaption({ text: '', show: true });
    const words = text.split(' ');
    let i = 0;
    captionTimer.current = setInterval(() => {
      i += 1;
      setCaption({ text: words.slice(0, i).join(' '), show: true });
      if (i >= words.length) {
        if (captionTimer.current) clearInterval(captionTimer.current);
        setTimeout(() => setSpeaking(false), 400);
      }
    }, 55);
  }, []);

  const runAlex = useCallback(
    (idx: number) => {
      const node = FLOW[idx];
      if (!node) return;
      setSuggest([]);
      setThinking(true);
      scrollDown();
      setTimeout(() => {
        setThinking(false);
        setMessages((m) => [...m, { role: 'alex', text: node.text, doc: node.doc ?? null }]);
        speak(node.text);
        setSuggest(node.suggest || []);
        setStep(idx);
        scrollDown();
      }, 900);
    },
    [speak, scrollDown]
  );

  useEffect(() => {
    const t = setTimeout(() => runAlex(0), 600);
    return () => clearTimeout(t);
  }, [runAlex]);

  useEffect(scrollDown, [messages, thinking]);

  const send = (text?: string) => {
    const val = (text ?? input).trim();
    if (!val || thinking) return;
    if (captionTimer.current) clearInterval(captionTimer.current);
    setSpeaking(false);
    setMessages((m) => [...m, { role: 'me', text: val, doc: null }]);
    setInput('');
    setSuggest([]);
    setMic(false);
    const next = step + 1;
    setTimeout(() => runAlex(next), 500);
  };

  const onChip = (c: string) => {
    if (c === 'Run mock trial') {
      router.push('/judge');
      return;
    }
    if (c === 'Open the package') {
      setOpenDoc('package');
      return;
    }
    send(c);
  };

  return (
    <div className="room">
      <div className={'stage' + (speaking ? ' speaking' : '')}>
        <div className="stage-top">
          <Link className="back-link" href="/">
            ← Prosecuto
          </Link>
          <span className="mode-pill">Lawyer Mode</span>
        </div>

        <div className="avatar-slot">
          <AvatarMount speaking={speaking} />
          <div className="avatar-info">
            <div className="avatar-fallback">
              <div className="ring">
                <span className="avatar-glyph">A</span>
              </div>
            </div>
            <div className="who-name serif">Alex</div>
            <div className="who-role">Lawyer · Case prep</div>
          </div>
        </div>

        <div className="caption">
          <div className={'caption-inner' + (caption.show ? ' show' : '')}>
            <span className="spk">
              Alex
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
            <h1 className="serif">Case preparation</h1>
            <div className="sub">Early Resolution &amp; Trial</div>
          </div>
          <div className="head-tabs">
            <button className={tab === 'chat' ? 'active' : ''} type="button" onClick={() => setTab('chat')}>
              Conversation
            </button>
            <button className={tab === 'docs' ? 'active' : ''} type="button" onClick={() => setTab('docs')}>
              Documents <span className="badge">{sharedDocs.length}</span>
            </button>
          </div>
        </div>

        {tab === 'chat' ? (
          <div className="transcript" ref={transcriptRef}>
            {messages.map((m, i) => {
              const meta = ROLE_META[m.role];
              return (
                <div key={i} className={'turn' + (m.role === 'me' ? ' me' : '')}>
                  <div className="meta">
                    <span className={'av ' + meta.av}>{meta.glyph}</span>
                    <span className="nm">{meta.nm}</span>
                    <span className="rl">{meta.rl}</span>
                  </div>
                  <div className="body">{m.text}</div>
                  {m.doc && (
                    <div className="doc-card" onClick={() => setOpenDoc(m.doc)} role="presentation">
                      <div className="dc-top">
                        <div className="dc-ico" />
                        <div>
                          <div className="dc-t">{DOCS[m.doc].title}</div>
                          <div className="dc-s">{DOCS[m.doc].sub}</div>
                        </div>
                        <div className="dc-open">Open →</div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {thinking && (
              <div className="turn">
                <div className="meta">
                  <span className="av alex">A</span>
                  <span className="nm">Alex</span>
                  <span className="rl">Lawyer</span>
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
          </div>
        ) : (
          <div className="transcript" ref={transcriptRef}>
            {sharedDocs.length === 0 && (
              <p style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: '13px' }}>
                No documents shared yet. Alex will share forms and case law as your case develops.
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
                <button key={i} className="chip" type="button" onClick={() => onChip(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
          <div className="input-row">
            <textarea
              rows={1}
              placeholder="Type your answer, or use the mic…"
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
              title="Voice input"
              onClick={() => setMic((v) => !v)}
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
