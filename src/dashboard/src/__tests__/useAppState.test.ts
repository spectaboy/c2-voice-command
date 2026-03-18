import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAppState } from '../hooks/useAppState';
import type { WSMessage } from '../types';

function makePositionMsg(uid: string, lat: number, lon: number): WSMessage {
  return {
    type: 'position_update',
    payload: {
      uid,
      callsign: uid,
      domain: 'air',
      affiliation: 'f',
      lat,
      lon,
      alt_m: 100,
      heading: 90,
      speed_mps: 12,
      battery_pct: 95,
      mode: 'GUIDED',
      armed: true,
    },
    timestamp: new Date().toISOString(),
  };
}

describe('useAppState', () => {
  it('initializes with empty state', () => {
    const { result } = renderHook(() => useAppState());
    expect(result.current.state.vehicles.size).toBe(0);
    expect(result.current.state.trails.size).toBe(0);
    expect(result.current.state.transcripts).toHaveLength(0);
    expect(result.current.state.iffAuditLog).toHaveLength(0);
    expect(result.current.state.pendingConfirmation).toBeNull();
    expect(result.current.state.connectionStatus).toBe('disconnected');
  });

  it('handles position_update — adds vehicle and trail', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.handleWSMessage(makePositionMsg('UAV-1', 45.0, -75.0));
    });

    expect(result.current.state.vehicles.size).toBe(1);
    expect(result.current.state.vehicles.get('UAV-1')!.lat).toBe(45.0);
    expect(result.current.state.trails.get('UAV-1')).toHaveLength(1);
  });

  it('caps trail length at 30', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      for (let i = 0; i < 35; i++) {
        result.current.handleWSMessage(makePositionMsg('UAV-1', 45 + i * 0.001, -75.0));
      }
    });

    expect(result.current.state.trails.get('UAV-1')).toHaveLength(30);
  });

  it('handles iff_change — updates affiliation and logs audit entry', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.handleWSMessage(makePositionMsg('UAV-1', 45.0, -75.0));
    });

    act(() => {
      result.current.handleWSMessage({
        type: 'iff_change',
        payload: {
          uid: 'UAV-1',
          affiliation: 'h',
          confidence: 0.9,
          threat_score: 0.8,
          indicators: ['intercept_course'],
          timestamp: new Date().toISOString(),
        },
        timestamp: new Date().toISOString(),
      });
    });

    expect(result.current.state.vehicles.get('UAV-1')!.affiliation).toBe('h');
    expect(result.current.state.iffAuditLog).toHaveLength(1);
    expect(result.current.state.iffAuditLog[0].previous_affiliation).toBe('f');
    expect(result.current.state.iffAuditLog[0].new_affiliation).toBe('h');
  });

  it('handles voice_transcript — appends to transcripts', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.handleWSMessage({
        type: 'voice_transcript',
        payload: {
          raw_transcript: 'move UAV-1 north',
          confidence: 0.92,
          timestamp: new Date().toISOString(),
        },
        timestamp: new Date().toISOString(),
      });
    });

    expect(result.current.state.transcripts).toHaveLength(1);
    expect(result.current.state.transcripts[0].raw_transcript).toBe('move UAV-1 north');
  });

  it('handles command_ack — stores ack by command_id', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.handleWSMessage({
        type: 'command_ack',
        payload: {
          command_id: 'cmd-123',
          status: 'completed',
          vehicle_callsign: 'UAV-1',
          timestamp: new Date().toISOString(),
        },
        timestamp: new Date().toISOString(),
      });
    });

    expect(result.current.state.commandAcks.get('cmd-123')!.status).toBe('completed');
  });

  it('handles confirmation_required and dismiss', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.handleWSMessage({
        type: 'confirmation_required',
        payload: {
          command_id: 'cmd-456',
          command_type: 'engage',
          vehicle_callsign: 'UAV-2',
          risk_level: 'critical',
          readback_text: 'CONFIRM engagement',
        },
        timestamp: new Date().toISOString(),
      });
    });

    expect(result.current.state.pendingConfirmation).not.toBeNull();
    expect(result.current.state.pendingConfirmation!.risk_level).toBe('critical');

    act(() => {
      result.current.dismissConfirmation();
    });

    expect(result.current.state.pendingConfirmation).toBeNull();
  });

  it('setConnectionStatus updates connection state', () => {
    const { result } = renderHook(() => useAppState());

    act(() => {
      result.current.setConnectionStatus('connected');
    });

    expect(result.current.state.connectionStatus).toBe('connected');
  });
});
