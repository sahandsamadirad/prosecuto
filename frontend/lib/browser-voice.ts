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

export function createSpeechRecognition(options: {
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
}) {
  if (!canUseSpeechRecognition()) {
    options.onError?.('This browser does not support speech recognition. Chrome works best.');
    return null;
  }

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-CA';

  recognition.onresult = (event) => {
    let interim = '';
    let finalText = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += text;
      else interim += text;
    }
    if (interim.trim()) options.onInterim?.(interim.trim());
    if (finalText.trim()) options.onFinal(finalText.trim());
  };

  recognition.onerror = (event) => {
    options.onError?.(event.error || 'Speech recognition failed.');
  };
  recognition.onend = () => options.onEnd?.();

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
  utterance.rate = 1.02;
  utterance.pitch = 1;
  utterance.voice = pickMaleEnglishVoice();

  utterance.onstart = () => options.onStart?.();
  utterance.onboundary = (event) => {
    const end = Math.max(0, event.charIndex || 0);
    options.onProgress?.(text.slice(0, end).trim() || text.split(' ').slice(0, 3).join(' '));
  };
  utterance.onend = () => options.onEnd?.();
  utterance.onerror = () => options.onEnd?.();

  window.speechSynthesis.speak(utterance);
}

function pickMaleEnglishVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;

  const english = voices.filter((voice) => voice.lang.toLowerCase().startsWith('en'));
  const maleHints = [
    'male',
    'man',
    'daniel',
    'david',
    'fred',
    'george',
    'alex',
    'aaron',
    'arthur',
    'oliver',
    'thomas',
    'matthew',
    'ryan',
    'guy',
  ];

  return (
    english.find((voice) => maleHints.some((hint) => voice.name.toLowerCase().includes(hint))) ||
    english.find((voice) => voice.lang.toLowerCase() === 'en-ca') ||
    english.find((voice) => voice.lang.toLowerCase().startsWith('en-us')) ||
    english[0] ||
    null
  );
}

export function stopSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}
