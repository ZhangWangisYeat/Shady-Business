export type VoiceQuery = { origin: string | null; destination: string };

export function parseVoiceQuery(transcript: string): VoiceQuery | null {
  const text = transcript.trim().replace(/[.!?。！？]+$/, '').trim();
  const pair = text.match(/^(?:take me )?from\s+(.+?)\s+to\s+(.+)$/i)
    ?? text.match(/^从\s*(.+?)\s*到\s*(.+)$/);
  if (pair) return { origin: pair[1].trim(), destination: pair[2].trim() };
  const single = text.match(/^(?:take me to|go to|to)\s+(.+)$/i)
    ?? text.match(/^(?:去|我要去|带我去)\s*(.+)$/);
  const destination = (single?.[1] ?? text).trim();
  return destination ? { origin: null, destination } : null;
}
