import { useEffect, useRef } from 'react';
import type { IFFAuditEntry } from '../types';
import { AFFILIATION_COLORS, AFFILIATION_LABELS } from '../types';

interface Props {
  entries: IFFAuditEntry[];
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-GB', { hour12: false });
  } catch {
    return iso;
  }
}

export default function IFFAuditTrail({ entries }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries.length]);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div className="panel-header">IFF AUDIT TRAIL</div>
      <div className="panel-body" style={{ flex: 1 }}>
        {entries.length === 0 ? (
          <div className="empty-state">NO IFF EVENTS</div>
        ) : (
          entries.map((e, i) => (
            <div className="iff-entry" key={i}>
              <span className="timestamp" style={{ color: '#6e7a86', fontSize: 10 }}>
                {formatTime(e.timestamp)}
              </span>{' '}
              <strong>{e.callsign}</strong>
              <span
                className="change-arrow"
                style={{ color: AFFILIATION_COLORS[e.previous_affiliation] }}
              >
                {' '}{AFFILIATION_LABELS[e.previous_affiliation]}
              </span>
              <span className="change-arrow">→</span>
              <span style={{ color: AFFILIATION_COLORS[e.new_affiliation], fontWeight: 700 }}>
                {AFFILIATION_LABELS[e.new_affiliation]}
              </span>
              <span
                className="threat-score"
                style={{
                  color: e.threat_score > 0.7 ? '#ff3333' : e.threat_score > 0.4 ? '#ffff00' : '#00ff88',
                }}
              >
                THREAT: {(e.threat_score * 100).toFixed(0)}%
              </span>
              {e.indicators.length > 0 && (
                <div className="indicators">{e.indicators.join(' · ')}</div>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
