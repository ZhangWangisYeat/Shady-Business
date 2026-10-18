import React, { useEffect, useRef, useState } from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { requestRecordingPermissionsAsync, useAudioStream } from 'expo-audio';
import { getVoiceToken } from '../api/client';
import { COLORS } from '../theme';

const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function base64(bytes: Uint8Array): string {
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i], b = bytes[i + 1], c = bytes[i + 2];
    out += alphabet[a >> 2] + alphabet[((a & 3) << 4) | ((b ?? 0) >> 4)]
      + (i + 1 < bytes.length ? alphabet[((b & 15) << 2) | ((c ?? 0) >> 6)] : '=')
      + (i + 2 < bytes.length ? alphabet[c & 63] : '=');
  }
  return out;
}

export function VoiceInput({ onTranscript }: { onTranscript: (text: string) => void }) {
  const [state, setState] = useState<'idle' | 'connecting' | 'listening' | 'processing'>('idle');
  const [message, setMessage] = useState('');
  const socket = useRef<WebSocket | null>(null);
  const lastChunk = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listening = useRef(false);
  const finish = (error = '') => {
    listening.current = false;
    stream.stop();
    socket.current?.close(); socket.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null; lastChunk.current = null;
    setState('idle'); setMessage(error);
  };
  const { stream } = useAudioStream({ sampleRate: 16000, channels: 1, encoding: 'int16', onBuffer: buffer => {
    if (!listening.current || !socket.current || socket.current.readyState !== WebSocket.OPEN) return;
    if (buffer.sampleRate !== 16000 || buffer.channels !== 1) { finish('Microphone format is not supported on this device.'); return; }
    const next = base64(new Uint8Array(buffer.data));
    if (lastChunk.current) socket.current.send(JSON.stringify({ message_type: 'input_audio_chunk', audio_base_64: lastChunk.current }));
    lastChunk.current = next;
  } });
  useEffect(() => () => { listening.current = false; stream.stop(); socket.current?.close(); if (timer.current) clearTimeout(timer.current); }, [stream]);

  const start = async () => {
    setMessage(''); setState('connecting');
    try {
      if (!(await requestRecordingPermissionsAsync()).granted) throw new Error('Microphone permission denied.');
      const { token } = await getVoiceToken();
      const ws = new WebSocket(`wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime&audio_format=pcm_16000&commit_strategy=manual&token=${encodeURIComponent(token)}`);
      socket.current = ws;
      ws.onopen = async () => {
        try { listening.current = true; await stream.start(); setState('listening'); timer.current = setTimeout(() => stop(), 12000); }
        catch { finish('Could not start the microphone.'); }
      };
      ws.onmessage = event => {
        let data: { message_type?: string; text?: string };
        try { data = JSON.parse(String(event.data)); } catch { return; }
        if (data.message_type === 'partial_transcript' && data.text) setMessage(data.text);
        if (data.message_type === 'committed_transcript') {
          const text = data.text?.trim() ?? '';
          finish(text ? '' : 'No speech was recognized. Please try again.');
          if (text) onTranscript(text);
        }
        if (data.message_type?.endsWith('error') || data.message_type === 'rate_limited') finish('Voice recognition is unavailable. Please try again.');
      };
      ws.onerror = () => finish('Voice connection failed. Please try again.');
      ws.onclose = () => { if (socket.current === ws) finish('Voice connection closed. Please try again.'); };
    } catch (e) { finish(e instanceof Error ? e.message : 'Voice input unavailable.'); }
  };
  const stop = () => {
    if (!listening.current) return;
    listening.current = false; stream.stop(); setState('processing');
    if (timer.current) clearTimeout(timer.current);
    if (lastChunk.current && socket.current?.readyState === WebSocket.OPEN)
      socket.current.send(JSON.stringify({ message_type: 'input_audio_chunk', audio_base_64: lastChunk.current, commit: true }));
    else { finish('No audio captured. Please try again.'); return; }
    timer.current = setTimeout(() => finish('Voice recognition timed out. Please try again.'), 8000);
  };
  return <View style={{ alignItems: 'center' }}>
    <TouchableOpacity accessibilityRole="button" accessibilityLabel={state === 'listening' ? 'Stop voice input' : 'Speak your route'}
      disabled={state === 'connecting' || state === 'processing'} onPress={state === 'listening' ? stop : start}
      style={{ paddingHorizontal: 9, paddingVertical: 5 }}>
      <Text style={{ color: COLORS.ink, fontSize: 19 }}>{state === 'listening' ? '■' : '🎤'}</Text>
    </TouchableOpacity>
    {!!message && <Text accessibilityLiveRegion="polite" style={{ color: COLORS.muted, fontSize: 10, maxWidth: 110 }} numberOfLines={2}>{message}</Text>}
  </View>;
}
