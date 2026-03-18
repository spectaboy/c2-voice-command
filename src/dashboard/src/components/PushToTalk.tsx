import { useRef, useState, useCallback, useEffect } from 'react';

const VOICE_WS_URL = `ws://${window.location.hostname}:8001/ws/voice`;
const SAMPLE_RATE = 16000;

export default function PushToTalk() {
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'ready' | 'recording' | 'processing' | 'error'>('idle');
  const [lastTranscript, setLastTranscript] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  // Connect to voice WebSocket
  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(VOICE_WS_URL);

    ws.onopen = () => {
      setStatus('ready');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.transcript) {
          setLastTranscript(data.transcript);
          setStatus('ready');
        }
      } catch {
        // ignore non-JSON
      }
    };

    ws.onerror = () => {
      setStatus('error');
    };

    ws.onclose = () => {
      setStatus('idle');
      wsRef.current = null;
    };

    wsRef.current = ws;
  }, []);

  // Initialize on mount
  useEffect(() => {
    connectWS();
    return () => {
      wsRef.current?.close();
      mediaStreamRef.current?.getTracks().forEach(t => t.stop());
      audioCtxRef.current?.close();
    };
  }, [connectWS]);

  const startRecording = useCallback(async () => {
    try {
      // Ensure WS is connected
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        connectWS();
        // Wait a bit for connection
        await new Promise(r => setTimeout(r, 500));
      }

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setStatus('error');
        return;
      }

      // Get mic access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      mediaStreamRef.current = stream;

      // Create audio context for resampling to 16kHz mono
      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      // Use ScriptProcessorNode (deprecated but widely supported)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // Send PTT start
      wsRef.current.send(JSON.stringify({ type: 'ptt_start' }));
      setIsRecording(true);
      setStatus('recording');

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) return;

        const float32 = e.inputBuffer.getChannelData(0);
        // Convert float32 [-1, 1] to int16
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          const s = Math.max(-1, Math.min(1, float32[i]));
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        wsRef.current.send(int16.buffer);
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);
    } catch (err) {
      console.error('Mic access failed:', err);
      setStatus('error');
    }
  }, [connectWS]);

  const stopRecording = useCallback(() => {
    // Stop audio processing
    processorRef.current?.disconnect();
    processorRef.current = null;
    mediaStreamRef.current?.getTracks().forEach(t => t.stop());
    mediaStreamRef.current = null;
    audioCtxRef.current?.close();
    audioCtxRef.current = null;

    // Send PTT stop to trigger transcription
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ptt_stop' }));
    }

    setIsRecording(false);
    setStatus('processing');
  }, []);

  const statusText: Record<string, string> = {
    idle: 'DISCONNECTED',
    connecting: 'CONNECTING...',
    ready: 'READY — HOLD SPACE OR CLICK TO TALK',
    recording: 'RECORDING...',
    processing: 'PROCESSING...',
    error: 'ERROR — CLICK TO RETRY',
  };

  const statusColor: Record<string, string> = {
    idle: '#666',
    connecting: '#ffff00',
    ready: '#00ff88',
    recording: '#ff3333',
    processing: '#ffff00',
    error: '#ff3333',
  };

  // Spacebar push-to-talk
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !e.repeat && !isRecording && status === 'ready') {
        e.preventDefault();
        startRecording();
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && isRecording) {
        e.preventDefault();
        stopRecording();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isRecording, status, startRecording, stopRecording]);

  return (
    <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '12px', borderTop: '1px solid #1a2332' }}>
      <button
        onMouseDown={() => { if (status === 'ready') startRecording(); else if (status === 'error') connectWS(); }}
        onMouseUp={() => { if (isRecording) stopRecording(); }}
        onMouseLeave={() => { if (isRecording) stopRecording(); }}
        style={{
          background: isRecording ? '#ff3333' : status === 'ready' ? '#1a3a2a' : '#1a2332',
          border: `2px solid ${statusColor[status]}`,
          color: statusColor[status],
          padding: '8px 20px',
          fontFamily: '"Share Tech Mono", monospace',
          fontSize: '13px',
          fontWeight: 'bold',
          cursor: 'pointer',
          textTransform: 'uppercase',
          minWidth: '60px',
          transition: 'all 0.15s',
        }}
      >
        {isRecording ? '⬤ REC' : 'PTT'}
      </button>
      <span style={{ color: statusColor[status], fontFamily: '"Share Tech Mono", monospace', fontSize: '11px' }}>
        {statusText[status]}
      </span>
      {lastTranscript && (
        <span style={{ color: '#8892a0', fontFamily: '"Share Tech Mono", monospace', fontSize: '11px', marginLeft: 'auto' }}>
          LAST: {lastTranscript.slice(0, 60)}
        </span>
      )}
    </div>
  );
}
