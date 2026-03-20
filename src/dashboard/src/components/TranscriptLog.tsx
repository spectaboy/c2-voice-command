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

function StatusIcon({ status }: { status?: string }) {
  switch (status) {
    case 'executed':
      return <span className="status-icon executed">&#x2713;</span>;
    case 'blocked':
      return <span className="status-icon blocked">&#x2717;</span>;
    case 'error':
      return <span className="status-icon error">!</span>;
    case 'confirmation':
      return <span className="status-icon confirmation">?</span>;
    default:
      return null;
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
          <div className="empty-state">AWAITING VOICE INPUT</div>
        ) : (
          transcripts.map((t, i) => (
            <div className={`transcript-entry ${t.status ? `status-${t.status}` : ''}`} key={i}>
              <div className="timestamp">{formatTime(t.timestamp)}</div>

              {/* System event: executed */}
              {t.status === 'executed' && (
                <div className="system-msg executed">
                  <StatusIcon status="executed" />
                  [{t.command_type?.toUpperCase()}] {t.vehicle_callsign} — {t.status_message}
                </div>
              )}

              {/* System event: blocked by IFF */}
              {t.status === 'blocked' && (
                <div className="system-msg blocked">
                  <StatusIcon status="blocked" />
                  {t.status_message}
                </div>
              )}

              {/* System event: error */}
              {t.status === 'error' && (
                <div className="system-msg error">
                  <StatusIcon status="error" />
                  {t.status_message}
                </div>
              )}

              {/* System event: confirmation required */}
              {t.status === 'confirmation' && (
                <div className="system-msg confirmation">
                  <StatusIcon status="confirmation" />
                  CONFIRM — {t.status_message}
                </div>
              )}

              {/* Regular voice transcript */}
              {!t.status && (
                <>
                  <div className="raw-text">&gt; {t.raw_transcript}</div>
                  {t.parsed_command && (
                    <div className="parsed-cmd">
                      [{t.parsed_command.command_type.toUpperCase()}] {t.parsed_command.vehicle_callsign}
                      {t.parsed_command.location && (
                        <> &rarr; {t.parsed_command.location.lat.toFixed(4)}, {t.parsed_command.location.lon.toFixed(4)}</>
                      )}
                    </div>
                  )}
                  <div
                    className="confidence-bar"
                    style={{ width: `${(t.confidence * 100).toFixed(0)}%`, maxWidth: '100%' }}
                    title={`Confidence: ${(t.confidence * 100).toFixed(0)}%`}
                  />
                </>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
