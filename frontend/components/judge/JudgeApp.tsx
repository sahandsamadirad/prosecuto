'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  asAgentText,
  asStateUpdate,
  createSession,
  sendUserText,
  textSocketUrl,
  type BackendStatus,
  type StateUpdatePayload,
  type WSMessage,
} from '@/lib/prosecuto-api';
import { createSpeechRecognition, requestMicrophoneAccess, speakText, stopSpeech } from '@/lib/browser-voice';
import { stripFormatting } from '@/lib/text';
import { CHARS, DOCS, PHASES, VERDICT, type CharKey, type JudgeDocKey } from './data';

const AvatarMount = dynamic(() => import('@/components/AvatarMount'), { ssr: false });

type Message = {
  role: CharKey;
  text: string | null;
  doc: JudgeDocKey | null;
};

const DEFENCE_CHIPS = [
  'I do solemnly affirm.',
  "I'm the registered owner, but I was not the driver.",
  'I respectfully ask that the charge be dismissed.',
];

const PHASE_INDEX: Record<string, number> = {
  idle: 0,
  clerk_call_to_order: 0,
  clerk_oath: 1,
  judge_open: 2,
  crown_opening: 3,
  defence_opening: 4,
  crown_case: 5,
  defence_cross_crown: 6,
  defence_case: 7,
  crown_cross_defence: 8,
  crown_closing: 9,
  defence_closing: 10,
  verdict: 11,
  feedback: 11,
  done: 11,
};

function speakerToRole(agent?: string | null): CharKey {
  if (!agent) return 'judge';
  if (agent.includes('clerk')) return 'clerk';
  if (agent.includes('crown') || agent.includes('prosecutor')) return 'crown';
  if (agent.includes('prosecuto')) return 'prosecuto';
  return 'judge';
}

function phaseFromSummary(update: StateUpdatePayload | null): string | null {
  const match = update?.summary?.match(/phase=([a-z_]+)/);
  return match?.[1] ?? null;
}

function docForCourtText(text: string): JudgeDocKey | null {
  const lower = text.toLowerCase();
  if (lower.includes('photograph') || lower.includes('photo')) return 'photo';
  if (lower.includes('camera operating') || lower.includes('calibration')) return 'camcert';
  if (lower.includes('certificate of offence')) return 'certificate';
  return null;
}

export default function JudgeApp() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [cur, setCur] = useState(0);
  const [suggest, setSuggest] = useState<string[]>(DEFENCE_CHIPS);
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
  const [status, setStatus] = useState<BackendStatus>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [stateUpdate, setStateUpdate] = useState<StateUpdatePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<ReturnType<typeof createSpeechRecognition> | null>(null);
  const tRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const capTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopSpeaking = useCallback(() => {
    if (capTimer.current) clearInterval(capTimer.current);
    stopSpeech();
    setSpeaking(false);
  }, []);

  const sharedDocs = Array.from(new Set(messages.filter((m) => m.doc).map((m) => m.doc!)));

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => {
      const el = tRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setMic(false);
  }, []);

  const speak = useCallback((who: CharKey, text: string) => {
    if (capTimer.current) clearInterval(capTimer.current);
    stopListening();
    setActive(who);
    setCaption({ who, text: '', show: true });
    speakText(text, {
      onStart: () => setSpeaking(true),
      onProgress: (spokenText) => setCaption({ who, text: spokenText || text, show: true }),
      onEnd: () => {
        setCaption({ who, text, show: true });
        setTimeout(() => setSpeaking(false), 300);
      },
    });
  }, [stopListening]);

  const connect = useCallback(async () => {
    setStatus('connecting');
    setThinking(true);
    setError(null);
    setMessages([]);
    setStateUpdate(null);
    setEnded(false);
    setSuggest(DEFENCE_CHIPS);
    socketRef.current?.close();

    try {
      const session = await createSession('judge');
      setSessionId(session.session_id);
      const ws = new WebSocket(textSocketUrl(session.session_id));
      socketRef.current = ws;

      ws.onopen = () => setStatus('thinking');
      ws.onerror = () => {
        setThinking(false);
        setStatus('error');
        setError('Backend socket error. Make sure FastAPI is running on port 8000.');
      };
      ws.onclose = () => {
        setThinking(false);
        setStatus((prev) => (prev === 'error' ? prev : 'idle'));
      };
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data) as WSMessage;
        const agentText = asAgentText(message);
        if (agentText) {
          const role = speakerToRole(agentText.agent);
          const clean = stripFormatting(agentText.text);
          setThinking(false);
          setStatus('connected');
          setMessages((m) => [...m, { role, text: clean, doc: docForCourtText(clean) }]);
          speak(role, clean);
          scrollDown();
          return;
        }

        const update = asStateUpdate(message);
        if (update) {
          const phase = phaseFromSummary(update);
          setThinking(false);
          setStatus('connected');
          setStateUpdate(update);
          setCur(phase ? PHASE_INDEX[phase] ?? 0 : 0);
          setEnded(phase === 'done');
          setSuggest(phase === 'done' ? [] : DEFENCE_CHIPS);
          return;
        }

        if (message.type === 'error') {
          setThinking(false);
          setStatus('error');
          setError(String(message.payload.message || 'Backend returned an error.'));
        }
      };
    } catch (exc) {
      setThinking(false);
      setStatus('error');
      setError(exc instanceof Error ? exc.message : 'Could not connect to backend.');
    }
  }, [scrollDown, speak]);

  useEffect(() => {
    connect();
    return () => {
      if (capTimer.current) clearInterval(capTimer.current);
      stopListening();
      stopSpeech();
      socketRef.current?.close();
    };
  }, [connect, stopListening]);

  useEffect(scrollDown, [messages, thinking, ended]);

  useEffect(() => {
    const el = captionRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [caption.text]);

  const send = (text?: string) => {
    const val = (text ?? input).trim();
    if (!val || thinking || ended) return;
    if (capTimer.current) clearInterval(capTimer.current);
    stopListening();
    stopSpeech();
    setSpeaking(false);
    setMessages((m) => [...m, { role: 'me', text: val, doc: null }]);
    setInput('');
    setSuggest([]);
    setThinking(true);
    setStatus('thinking');
    if (!sendUserText(socketRef.current, sessionId, val)) {
      setThinking(false);
      setStatus('error');
      setError('Not connected to the backend yet. Try reconnecting.');
    }
  };

  const toggleMic = async () => {
    if (mic) {
      stopListening();
      return;
    }

    // Barge-in: starting the mic interrupts the court so it listens to the user.
    stopSpeaking();

    try {
      await requestMicrophoneAccess();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Microphone permission was denied.');
      return;
    }

    const recognition = createSpeechRecognition({
      onInterim: (text) => setInput(text),
      onFinal: (text) => {
        setMic(false);
        setInput('');
        send(text);
      },
      onEnd: () => setMic(false),
      onError: (message) => {
        setMic(false);
        if (message === 'aborted' || message === 'no-speech') return;
        setError(message);
      },
    });
    recognitionRef.current = recognition;
    if (!recognition) return;
    setMic(true);
    try {
      recognition.start();
    } catch (exc) {
      setMic(false);
      setError(exc instanceof Error ? exc.message : 'Could not start microphone speech recognition.');
    }
  };

  const aMeta = CHARS[active];

  return (
    <div className="room">
      <div className={'stage' + (speaking ? ' speaking' : '')}>
        <div className="stage-top">
          <Link className="back-link" href="/">
            ← Prosecuto
          </Link>
          <span className="mode-pill">Judge Mode · Backend trial</span>
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
          {speaking && (
            <button className="caption-stop" type="button" onClick={stopSpeaking} title="Stop">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
              Stop
            </button>
          )}
          <div className={'caption-inner' + (caption.show ? ' show' : '')} ref={captionRef}>
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
            <div className="sub">Backend session {sessionId ? sessionId.slice(0, 8) : 'connecting'}</div>
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

        <div className={'backend-strip ' + status}>
          <span>{status === 'thinking' ? 'Court graph is running' : `Backend: ${status}`}</span>
          {stateUpdate?.summary && <span>{stateUpdate.summary}</span>}
          {error && <button type="button" onClick={connect}>Reconnect</button>}
        </div>

        <div className="rail">
          {PHASES.map((p, i) => (
            <div key={i} className={'ph' + (i === cur && !ended ? ' cur' : '') + (i < cur || ended ? ' done' : '')}>
              <span className="dot">{i < cur || ended ? '✓' : i + 1}</span>
              <span className="lb">{p.rail}</span>
            </div>
          ))}
        </div>

        {tab === 'chat' ? (
          <div className="transcript" ref={tRef}>
            {messages.map((m, i) => {
              const meta = CHARS[m.role];
              return (
                <div key={i} className={'turn' + (m.role === 'me' ? ' me' : '')}>
                  <div className="meta">
                    <span className={'av ' + meta.av}>{meta.glyph}</span>
                    <span className="nm">{meta.nm}</span>
                    <span className="rl">{meta.rl}</span>
                  </div>
                  {m.text && <div className="body">{m.text}</div>}
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
                    <div className="vlabel">The backend court graph has concluded</div>
                    <div className="vresult serif">{VERDICT.result}</div>
                  </div>
                  <div className="vline">Review the judge&apos;s final backend feedback in the transcript above.</div>
                </div>
                <div className="feedback-card">
                  <div className="verdict-actions">
                    <button className="btn btn-primary" type="button" onClick={connect}>
                      Run it again
                    </button>
                    <Link className="btn btn-ghost" href="/lawyer">
                      Back to prep with Alex
                    </Link>
                  </div>
                </div>
              </div>
            )}
            {error && <div className="error-note">{error}</div>}
          </div>
        ) : (
          <div className="transcript" ref={tRef}>
            {sharedDocs.length === 0 && <p className="empty-note">No exhibits detected in backend transcript yet.</p>}
            {sharedDocs.map((d, i) => (
              <div key={i} className="doc-card" style={{ marginBottom: '14px' }} onClick={() => setOpenDoc(d)} role="presentation">
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
              placeholder={ended ? 'The trial has concluded.' : 'Address the court when it is your turn…'}
              value={input}
              disabled={status === 'connecting' || ended}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className={'icon-btn mic' + (mic ? ' live' : '')} type="button" onClick={toggleMic} title={mic ? 'Stop voice input' : 'Start voice input'}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
              </svg>
            </button>
            <button className="icon-btn send-btn" type="button" disabled={!input.trim() || thinking || ended} onClick={() => send()} title="Send">
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
