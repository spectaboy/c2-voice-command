import { describe, it, expect } from 'vitest';
import type {
  VehicleStatus,
  IFFAssessment,
  WSMessage,
  CommandAck,
  VoiceTranscript,
  ConfirmationRequest,
} from '../types';
import { AFFILIATION_COLORS, AFFILIATION_LABELS, MAX_TRAIL_LENGTH } from '../types';

describe('types and constants', () => {
  it('AFFILIATION_COLORS has all affiliations', () => {
    expect(AFFILIATION_COLORS.f).toBe('#00ff88');
    expect(AFFILIATION_COLORS.h).toBe('#ff3333');
    expect(AFFILIATION_COLORS.u).toBe('#ffff00');
    expect(AFFILIATION_COLORS.n).toBe('#00aaff');
  });

  it('AFFILIATION_LABELS has all affiliations', () => {
    expect(AFFILIATION_LABELS.f).toBe('FRIENDLY');
    expect(AFFILIATION_LABELS.h).toBe('HOSTILE');
    expect(AFFILIATION_LABELS.u).toBe('UNKNOWN');
    expect(AFFILIATION_LABELS.n).toBe('NEUTRAL');
  });

  it('MAX_TRAIL_LENGTH is 30', () => {
    expect(MAX_TRAIL_LENGTH).toBe(30);
  });

  it('VehicleStatus shape is valid', () => {
    const v: VehicleStatus = {
      uid: 'SITL-UAV-01',
      callsign: 'UAV-1',
      domain: 'air',
      affiliation: 'f',
      lat: 45.3170,
      lon: -75.6700,
      alt_m: 100,
      heading: 90,
      speed_mps: 12.5,
      battery_pct: 95,
      mode: 'GUIDED',
      armed: true,
    };
    expect(v.uid).toBe('SITL-UAV-01');
    expect(v.domain).toBe('air');
    expect(v.armed).toBe(true);
  });

  it('IFFAssessment shape is valid', () => {
    const iff: IFFAssessment = {
      uid: 'SITL-UAV-03',
      affiliation: 'h',
      confidence: 0.85,
      threat_score: 0.78,
      indicators: ['intercept_course', 'high_speed_anomaly'],
      timestamp: '2026-03-17T14:30:00Z',
    };
    expect(iff.indicators).toHaveLength(2);
    expect(iff.threat_score).toBeGreaterThan(0.5);
  });

  it('WSMessage shape is valid', () => {
    const msg: WSMessage = {
      type: 'position_update',
      payload: { uid: 'test' },
      timestamp: new Date().toISOString(),
    };
    expect(msg.type).toBe('position_update');
  });

  it('CommandAck shape is valid', () => {
    const ack: CommandAck = {
      command_id: 'abc-123',
      status: 'completed',
      vehicle_callsign: 'UAV-1',
      timestamp: new Date().toISOString(),
    };
    expect(ack.status).toBe('completed');
  });

  it('VoiceTranscript shape is valid', () => {
    const t: VoiceTranscript = {
      raw_transcript: 'Alpha UAV proceed to waypoint bravo',
      confidence: 0.94,
      timestamp: new Date().toISOString(),
    };
    expect(t.confidence).toBeGreaterThan(0.9);
  });

  it('ConfirmationRequest shape is valid', () => {
    const req: ConfirmationRequest = {
      command_id: 'cmd-456',
      command_type: 'engage',
      vehicle_callsign: 'UAV-2',
      risk_level: 'critical',
      readback_text: 'CONFIRM: engage hostile',
    };
    expect(req.risk_level).toBe('critical');
  });
});
