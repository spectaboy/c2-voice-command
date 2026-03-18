import { useEffect, useRef } from 'react';
import type { VoiceTranscript } from '../types';

interface Props {
  transcripts: VoiceTranscript[];
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-GB', { hour12: false });
  } catch {
    return iso;
  }
}

export default function TranscriptLog({ transcripts }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts.length]);

  return (
    <div className="panel">
      <div className="panel-header">VOICE TRANSCRIPT</div>
      <div className="panel-body">
        {transcripts.length === 0 ? (
          <div className="empty-state">NO TRANSCRIPTS</div>
        ) : (
          transcripts.map((t, i) => (
            <div className="transcript-entry" key={i}>
              <div className="timestamp">{formatTime(t.timestamp)}</div>
              <div className="raw-text">&gt; {t.raw_transcript}</div>
              {t.parsed_command && (
                <div className="parsed-cmd">
                  [{t.parsed_command.command_type.toUpperCase()}] {t.parsed_command.vehicle_callsign}
                  {t.parsed_command.location && (
                    <> → {t.parsed_command.location.lat.toFixed(4)}, {t.parsed_command.location.lon.toFixed(4)}</>
                  )}
                </div>
              )}
              <div
                className="confidence-bar"
                style={{ width: `${(t.confidence * 100).toFixed(0)}%`, maxWidth: '100%' }}
                title={`Confidence: ${(t.confidence * 100).toFixed(0)}%`}
              />
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
