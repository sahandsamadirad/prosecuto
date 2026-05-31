/**
 * Flatten markdown / LaTeX that the model sometimes emits into plain prose,
 * so the transcript and captions read like a normal text message (and TTS
 * doesn't read symbols aloud).
 */
export function stripFormatting(input: string): string {
  if (!input) return '';
  let s = input;

  // Fenced + inline code → keep the content only.
  s = s.replace(/```[a-zA-Z0-9]*\n?([\s\S]*?)```/g, '$1');
  s = s.replace(/`([^`]+)`/g, '$1');

  // Markdown links [text](url) → text.
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

  // LaTeX math delimiters → inner content.
  s = s.replace(/\$\$([\s\S]*?)\$\$/g, '$1');
  s = s.replace(/\$([^$\n]+)\$/g, '$1');
  s = s.replace(/\\\(([\s\S]*?)\\\)/g, '$1');
  s = s.replace(/\\\[([\s\S]*?)\\\]/g, '$1');

  // LaTeX commands: \text{x} → x, bare \cmd → '' , then drop stray braces.
  s = s.replace(/\\[a-zA-Z]+\*?\s*\{([^{}]*)\}/g, '$1');
  s = s.replace(/\\[a-zA-Z]+\*?/g, '');
  s = s.replace(/[{}]/g, '');

  // Bold / italic emphasis markers.
  s = s.replace(/(\*\*|__)(.*?)\1/gs, '$2');
  s = s.replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s).,!?:;]|$)/g, '$1$2');

  // Line-start markdown: headers, quotes, bullet markers, rules.
  s = s.replace(/^[ \t]{0,3}#{1,6}[ \t]*/gm, '');
  s = s.replace(/^[ \t]{0,3}>[ \t]?/gm, '');
  s = s.replace(/^[ \t]{0,3}[-*+][ \t]+/gm, '');
  s = s.replace(/^[ \t]*([-*_])\1{2,}[ \t]*$/gm, '');

  // Tidy whitespace.
  s = s.replace(/[ \t]{2,}/g, ' ');
  s = s.replace(/\n{3,}/g, '\n\n');

  return s.trim();
}
