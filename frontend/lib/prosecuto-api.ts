export type ProsecutoMode = 'lawyer' | 'judge';

export type BackendStatus = 'idle' | 'connecting' | 'connected' | 'thinking' | 'error';

export type CreateSessionResponse = {
  session_id: string;
  mode: ProsecutoMode;
};

export type WSMessage = {
  type: 'agent_text' | 'state_update' | 'error' | string;
  session_id: string;
  seq: number;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type AgentTextPayload = {
  text: string;
  agent?: string | null;
};

export type StateUpdatePayload = {
  current_agent?: string | null;
  chosen_path?: string | null;
  summary?: string | null;
  flags?: string[];
};

const DEFAULT_HTTP = 'http://localhost:8000';
const DEFAULT_WS = 'ws://localhost:8000';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || DEFAULT_HTTP;
export const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE || API_BASE.replace(/^http/, 'ws') || DEFAULT_WS;

export async function createSession(mode: ProsecutoMode): Promise<CreateSessionResponse> {
  const res = await fetch(`${API_BASE}/api/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) {
    throw new Error(`Could not create ${mode} session (${res.status})`);
  }
  return res.json();
}

export function textSocketUrl(sessionId: string): string {
  return `${WS_BASE}/ws/text/${sessionId}`;
}

export function asAgentText(message: WSMessage): AgentTextPayload | null {
  if (message.type !== 'agent_text') return null;
  const text = message.payload.text;
  if (typeof text !== 'string') return null;
  const agent = typeof message.payload.agent === 'string' ? message.payload.agent : null;
  return { text, agent };
}

export function asStateUpdate(message: WSMessage): StateUpdatePayload | null {
  if (message.type !== 'state_update') return null;
  return {
    current_agent:
      typeof message.payload.current_agent === 'string' ? message.payload.current_agent : null,
    chosen_path: typeof message.payload.chosen_path === 'string' ? message.payload.chosen_path : null,
    summary: typeof message.payload.summary === 'string' ? message.payload.summary : null,
    flags: Array.isArray(message.payload.flags) ? message.payload.flags.filter((f): f is string => typeof f === 'string') : [],
  };
}

export function sendUserText(socket: WebSocket | null, sessionId: string | null, text: string): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN || !sessionId) return false;
  socket.send(
    JSON.stringify({
      type: 'user_text',
      session_id: sessionId,
      payload: { text },
    })
  );
  return true;
}
