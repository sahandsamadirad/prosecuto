'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
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
import { createSpeechRecognition, speakText, stopSpeech } from '@/lib/browser-voice';
import { DOCS, type DocKey } from './docs';
import { ROLE_META } from './flow';

const AvatarMount = dynamic(() => import('@/components/AvatarMount'), { ssr: false });

type Message = {
  role: 'alex' | 'me';
  text: string;
  doc: DocKey | null;
};

const STARTER_CHIPS = [
  'I got a red light camera ticket in Toronto.',
  'The ticket date was March 3, 2026 at Hurontario & Eglinton.',
  "I don't have all the details in front of me.",
];

const PATH_CHIPS = ['Early resolution', 'Screening review', 'Trial', 'Pay'];

function suggestionsFor(update: StateUpdatePayload | null): string[] {
  if (update?.chosen_path) return [];
  if (update?.current_agent === 'procedure_map' || update?.summary?.includes('procedure_map')) {
    return PATH_CHIPS;
  }
  return STARTER_CHIPS;
}

function docForText(text: string): DocKey | null {
  const lower = text.toLowerCase();
  if (lower.includes('disclosure')) return 'caselaw';
  if (lower.includes('package') || lower.includes('early resolution') || lower.includes('trial prep')) return 'package';
  if (lower.includes('statutory declaration') || lower.includes('sworn declaration')) return 'statdec';
  return null;
}

export default function LawyerApp() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggest, setSuggest] = useState<string[]>(STARTER_CHIPS);
  const [input, setInput] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState({ text: '', show: false });
  const [thinking, setThinking] = useState(false);
  const [tab, setTab] = useState<'chat' | 'docs'>('chat');
  const [openDoc, setOpenDoc] = useState<DocKey | null>(null);
  const [mic, setMic] = useState(false);
  const [status, setStatus] = useState<BackendStatus>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [stateUpdate, setStateUpdate] = useState<StateUpdatePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<ReturnType<typeof createSpeechRecognition> | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const captionTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const sharedDocs = Array.from(new Set(messages.filter((m) => m.doc).map((m) => m.doc!)));

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => {
      const el = transcriptRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const speak = useCallback((text: string) => {
    if (captionTimer.current) clearInterval(captionTimer.current);
    setCaption({ text: '', show: true });
    speakText(text, {
      onStart: () => setSpeaking(true),
      onProgress: (spokenText) => setCaption({ text: spokenText || text, show: true }),
      onEnd: () => {
        setCaption({ text, show: true });
        setTimeout(() => setSpeaking(false), 300);
      },
    });
  }, []);

  const connect = useCallback(async () => {
    setStatus('connecting');
    setError(null);
    setMessages([]);
    setStateUpdate(null);
    setSuggest(STARTER_CHIPS);
    socketRef.current?.close();

    try {
      const session = await createSession('lawyer');
      setSessionId(session.session_id);
      const ws = new WebSocket(textSocketUrl(session.session_id));
      socketRef.current = ws;

      ws.onopen = () => setStatus('connected');
      ws.onerror = () => {
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
          setThinking(false);
          setStatus('connected');
          setMessages((m) => [...m, { role: 'alex', text: agentText.text, doc: docForText(agentText.text) }]);
          speak(agentText.text);
          scrollDown();
          return;
        }

        const update = asStateUpdate(message);
        if (update) {
          setThinking(false);
          setStatus('connected');
          setStateUpdate(update);
          setSuggest(suggestionsFor(update));
          return;
        }

        if (message.type === 'error') {
          setThinking(false);
          setStatus('error');
          setError(String(message.payload.message || 'Backend returned an error.'));
        }
      };
    } catch (exc) {
      setStatus('error');
      setError(exc instanceof Error ? exc.message : 'Could not connect to backend.');
    }
  }, [scrollDown, speak]);

  useEffect(() => {
    connect();
    return () => {
      if (captionTimer.current) clearInterval(captionTimer.current);
      recognitionRef.current?.abort();
      stopSpeech();
      socketRef.current?.close();
    };
  }, [connect]);

  useEffect(scrollDown, [messages, thinking]);

  const send = (text?: string) => {
    const val = (text ?? input).trim();
    if (!val || thinking) return;
    if (captionTimer.current) clearInterval(captionTimer.current);
    stopSpeech();
    setSpeaking(false);
    setMessages((m) => [...m, { role: 'me', text: val, doc: null }]);
    setInput('');
    setSuggest([]);
    setMic(false);
    setThinking(true);
    setStatus('thinking');
    if (!sendUserText(socketRef.current, sessionId, val)) {
      setThinking(false);
      setStatus('error');
      setError('Not connected to the backend yet. Try reconnecting.');
    }
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

  const toggleMic = () => {
    if (mic) {
      recognitionRef.current?.stop();
      setMic(false);
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
        setError(message);
      },
    });
    recognitionRef.current = recognition;
    if (!recognition) return;
    setMic(true);
    recognition.start();
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
            <div className="sub">Backend session {sessionId ? sessionId.slice(0, 8) : 'connecting'}</div>
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

        <div className={'backend-strip ' + status}>
          <span>{status === 'thinking' ? 'Alex is running the backend graph' : `Backend: ${status}`}</span>
          {stateUpdate?.summary && <span>{stateUpdate.summary}</span>}
          {error && <button type="button" onClick={connect}>Reconnect</button>}
        </div>

        {tab === 'chat' ? (
          <div className="transcript" ref={transcriptRef}>
            {messages.length === 0 && !thinking && (
              <p className="empty-note">Connected to the backend. Send the first ticket detail to start Lawyer Mode.</p>
            )}
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
            {error && <div className="error-note">{error}</div>}
          </div>
        ) : (
          <div className="transcript" ref={transcriptRef}>
            {sharedDocs.length === 0 && <p className="empty-note">No documents inferred from backend responses yet.</p>}
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
                <button key={i} className="chip" type="button" onClick={() => onChip(s)}>
                  {s}
                </button>
              ))}
              {stateUpdate?.chosen_path && (
                <button className="chip" type="button" onClick={() => router.push('/judge')}>
                  Run mock trial
                </button>
              )}
            </div>
          )}
          <div className="input-row">
            <textarea
              rows={1}
              placeholder="Type your answer, or use the mic…"
              value={input}
              disabled={status === 'connecting'}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className={'icon-btn mic' + (mic ? ' live' : '')} type="button" title={mic ? 'Stop voice input' : 'Start voice input'} onClick={toggleMic}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
              </svg>
            </button>
            <button className="icon-btn send-btn" type="button" disabled={!input.trim() || thinking} onClick={() => send()} title="Send">
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
