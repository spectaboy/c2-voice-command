import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import IFFAuditTrail from '../../components/IFFAuditTrail';
import type { IFFAuditEntry } from '../../types';

describe('IFFAuditTrail', () => {
  it('shows empty state when no entries', () => {
    render(<IFFAuditTrail entries={[]} />);
    expect(screen.getByText('NO IFF EVENTS')).toBeInTheDocument();
  });

  it('renders an IFF entry with affiliation change', () => {
    const entries: IFFAuditEntry[] = [
      {
        uid: 'SITL-UAV-03',
        callsign: 'UAV-3',
        previous_affiliation: 'u',
        new_affiliation: 'h',
        threat_score: 0.78,
        indicators: ['intercept_course', 'high_speed_anomaly'],
        timestamp: '2026-03-17T14:30:00Z',
      },
    ];
    render(<IFFAuditTrail entries={entries} />);
    expect(screen.getByText('UAV-3')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText('HOSTILE')).toBeInTheDocument();
    expect(screen.getByText('THREAT: 78%')).toBeInTheDocument();
    expect(screen.getByText('intercept_course · high_speed_anomaly')).toBeInTheDocument();
  });
});
