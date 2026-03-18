import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TranscriptLog from '../../components/TranscriptLog';
import type { VoiceTranscript } from '../../types';

describe('TranscriptLog', () => {
  it('shows empty state when no transcripts', () => {
    render(<TranscriptLog transcripts={[]} />);
    expect(screen.getByText('NO TRANSCRIPTS')).toBeInTheDocument();
  });

  it('renders a transcript entry', () => {
    const transcripts: VoiceTranscript[] = [
      {
        raw_transcript: 'Alpha UAV proceed to waypoint bravo',
        confidence: 0.94,
        timestamp: '2026-03-17T14:30:00Z',
      },
    ];
    render(<TranscriptLog transcripts={transcripts} />);
    expect(screen.getByText(/Alpha UAV proceed to waypoint bravo/)).toBeInTheDocument();
  });

  it('renders parsed command when present', () => {
    const transcripts: VoiceTranscript[] = [
      {
        raw_transcript: 'move UAV-1 north',
        confidence: 0.9,
        parsed_command: {
          command_id: 'c1',
          command_type: 'move',
          vehicle_callsign: 'UAV-1',
          domain: 'air',
          location: { lat: 45.32, lon: -75.67, alt_m: 100 },
          parameters: {},
          raw_transcript: 'move UAV-1 north',
          risk_level: 'low',
          requires_confirmation: false,
          timestamp: '2026-03-17T14:30:00Z',
        },
        timestamp: '2026-03-17T14:30:00Z',
      },
    ];
    render(<TranscriptLog transcripts={transcripts} />);
    expect(screen.getByText(/MOVE/)).toBeInTheDocument();
    expect(screen.getAllByText(/UAV-1/).length).toBeGreaterThanOrEqual(1);
  });
});
