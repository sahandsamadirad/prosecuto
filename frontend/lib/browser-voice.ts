type SpeechRecognitionEventLike = Event & {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: { transcript: string };
    };
  };
};

type SpeechRecognitionErrorLike = Event & {
  error?: string;
};

type SpeechRecognitionLike = EventTarget & {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
    SpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export function canUseSpeechRecognition(): boolean {
  if (typeof window === 'undefined') return false;
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export async function requestMicrophoneAccess(): Promise<void> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser cannot access the microphone. Use Chrome on http://localhost:3000.');
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((track) => track.stop());
}

export function createSpeechRecognition(options: {
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
}) {
  if (!canUseSpeechRecognition()) {
    options.onError?.('This browser does not support speech-to-text. Use Chrome; Firefox does not support this mic flow.');
    return null;
  }

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-CA';

  // Don't send on the first final chunk — give the speaker time to pause and
  // keep going. Commit the accumulated transcript only after a real silence.
  const SILENCE_MS = 1800;
  let finalBuffer = '';
  let silenceTimer: ReturnType<typeof setTimeout> | null = null;

  const clearSilence = () => {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
  };

  const commit = () => {
    clearSilence();
    const text = finalBuffer.trim();
    finalBuffer = '';
    if (text) options.onFinal(text);
  };

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalBuffer += text + ' ';
      else interim += text;
    }
    const preview = (finalBuffer + interim).trim();
    if (preview) options.onInterim?.(preview);
    clearSilence();
    silenceTimer = setTimeout(commit, SILENCE_MS);
  };

  recognition.onerror = (event) => {
    const err = event.error || 'Speech recognition failed.';
    if (err === 'no-speech') return; // keep listening through quiet gaps
    options.onError?.(err);
  };
  recognition.onend = () => {
    commit(); // flush whatever was captured before the engine stopped
    options.onEnd?.();
  };

  // Stopping should send what we have, not drop it.
  const nativeStop = recognition.stop.bind(recognition);
  recognition.stop = () => {
    commit();
    nativeStop();
  };

  return recognition;
}

export function speakText(
  text: string,
  options: {
    onStart?: () => void;
    onProgress?: (spokenText: string) => void;
    onEnd?: () => void;
  } = {}
) {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    options.onStart?.();
    options.onProgress?.(text);
    globalThis.setTimeout(() => options.onEnd?.(), Math.min(3000, Math.max(800, text.length * 18)));
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-CA';
  utterance.rate = 0.96;
  utterance.pitch = 0.72;
  const voice = getMaleVoice();
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang; // keep engine from overriding with a default (female) voice
  }

  utterance.onstart = () => options.onStart?.();
  utterance.onboundary = (event) => {
    const end = Math.max(0, event.charIndex || 0);
    options.onProgress?.(text.slice(0, end).trim() || text.split(' ').slice(0, 3).join(' '));
  };
  utterance.onend = () => options.onEnd?.();
  utterance.onerror = () => options.onEnd?.();

  window.speechSynthesis.speak(utterance);
}

// One single male voice, reused for every character so the avatar never speaks
// in a woman's voice and never switches voices mid-app.
let cachedVoice: SpeechSynthesisVoice | null = null;

const MALE_PRIORITY = [
  'google uk english male',
  'microsoft david',
  'microsoft mark',
  'microsoft guy',
  'daniel',
  'alex',
  'fred',
  'oliver',
  'arthur',
  'thomas',
  'aaron',
  'reed',
  'rocko',
  'george',
  'matthew',
  'ryan',
  'guy',
];

const FEMALE_HINTS = [
  'female',
  'woman',
  'samantha',
  'victoria',
  'karen',
  'moira',
  'tessa',
  'fiona',
  'zira',
  'susan',
  'allison',
  'ava',
  'serena',
  'catherine',
  'kate',
  'zoe',
  'veena',
  'linda',
  'heather',
  'english female',
];

function isFemaleVoice(name: string): boolean {
  const n = name.toLowerCase();
  return FEMALE_HINTS.some((hint) => n.includes(hint));
}

function chooseMaleVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;

  const english = voices.filter((v) => v.lang.toLowerCase().startsWith('en'));
  const pool = english.length ? english : voices;

  for (const hint of MALE_PRIORITY) {
    const hit = pool.find((v) => v.name.toLowerCase().includes(hint));
    if (hit) return hit;
  }
  // No named male voice — at least avoid the known female ones.
  return pool.find((v) => !isFemaleVoice(v.name)) || null;
}

function getMaleVoice(): SpeechSynthesisVoice | null {
  if (cachedVoice) return cachedVoice;
  cachedVoice = chooseMaleVoice();
  return cachedVoice;
}

// Warm the voice list on load so even the very first (judge opening) utterance,
// which fires immediately on connect, already has the male voice chosen.
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => {
    cachedVoice = chooseMaleVoice();
  };
}

export function stopSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}
