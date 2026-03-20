import { useEffect, useRef } from 'react';
import type { WSMessage, AppState } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type StatusHandler = (status: AppState['connectionStatus']) => void;

// 6 vehicles around Halifax Harbor (44.6488, -63.5752)
const MOCK_VEHICLES = [
  { uid: 'SITL-UAV-1', callsign: 'UAV-1', domain: 'air' as const, lat: 44.6488, lon: -63.5752, alt_m: 100, heading: 90 },
  { uid: 'SITL-UAV-2', callsign: 'UAV-2', domain: 'air' as const, lat: 44.6538, lon: -63.5700, alt_m: 120, heading: 180 },
  { uid: 'SITL-UAV-3', callsign: 'UAV-3', domain: 'air' as const, lat: 44.6440, lon: -63.5680, alt_m: 80, heading: 270 },
  { uid: 'SITL-UGV-1', callsign: 'UGV-1', domain: 'ground' as const, lat: 44.6438, lon: -63.5800, alt_m: 0, heading: 45 },
  { uid: 'SITL-UGV-2', callsign: 'UGV-2', domain: 'ground' as const, lat: 44.6420, lon: -63.5830, alt_m: 0, heading: 315 },
  { uid: 'SITL-USV-1', callsign: 'USV-1', domain: 'maritime' as const, lat: 44.6380, lon: -63.5620, alt_m: 0, heading: 135 },
];

function jitter(val: number, range: number): number {
  return val + (Math.random() - 0.5) * range;
}

export function useMockData(
  enabled: boolean,
  onMessage: MessageHandler,
  onStatus: StatusHandler,
) {
  const tickRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;

    onStatus('connected');

    const interval = setInterval(() => {
      tickRef.current += 1;

      // Position updates for all vehicles
      for (const v of MOCK_VEHICLES) {
        const drift = tickRef.current * 0.0001;
        const idx = MOCK_VEHICLES.indexOf(v);
        const msg: WSMessage = {
          type: 'position_update',
          payload: {
            uid: v.uid,
            callsign: v.callsign,
            domain: v.domain,
            affiliation: 'f',
            lat: v.lat + Math.sin(drift + idx) * 0.002,
            lon: v.lon + Math.cos(drift + idx) * 0.002,
            alt_m: jitter(v.alt_m, 5),
            heading: (v.heading + tickRef.current * 2) % 360,
            speed_mps: jitter(12, 4),
            battery_pct: Math.max(20, 95 - tickRef.current * 0.1),
            mode: 'GUIDED',
            armed: true,
          },
          timestamp: new Date().toISOString(),
        };
        onMessage(msg);
      }

      // Voice transcript
      if (tickRef.current === 5) {
        onMessage({
          type: 'voice_transcript',
          payload: {
            raw_transcript: 'Alpha take off to 20 meters',
            confidence: 0.94,
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Execution readback
      if (tickRef.current === 7) {
        onMessage({
          type: 'command_result',
          payload: {
            status: 'executed',
            command_type: 'takeoff',
            vehicle_callsign: 'UAV-1',
            message: 'UAV-1 taking off to 20 meters.',
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Another voice transcript
      if (tickRef.current === 12) {
        onMessage({
          type: 'voice_transcript',
          payload: {
            raw_transcript: 'Bravo fly to waypoint Charlie',
            confidence: 0.91,
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Move execution
      if (tickRef.current === 14) {
        onMessage({
          type: 'command_result',
          payload: {
            status: 'executed',
            command_type: 'move',
            vehicle_callsign: 'UAV-2',
            message: 'UAV-2 proceeding to target location.',
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // IFF event
      if (tickRef.current === 18) {
        onMessage({
          type: 'iff_change',
          payload: {
            uid: 'SITL-UAV-3',
            affiliation: 'h',
            confidence: 0.85,
            threat_score: 0.78,
            indicators: ['intercept_course', 'high_speed_anomaly'],
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Try to engage friendly — BLOCKED
      if (tickRef.current === 22) {
        onMessage({
          type: 'voice_transcript',
          payload: {
            raw_transcript: 'Engage the friendly patrol',
            confidence: 0.88,
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      if (tickRef.current === 24) {
        onMessage({
          type: 'command_result',
          payload: {
            status: 'blocked',
            command_type: 'engage',
            vehicle_callsign: 'UAV-1',
            message: 'BLOCKED: friendly-patrol is classified FRIENDLY. Engagement denied to prevent fratricide.',
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Engage hostile — confirmation required
      if (tickRef.current === 30) {
        onMessage({
          type: 'voice_transcript',
          payload: {
            raw_transcript: 'Alpha engage the hostile target',
            confidence: 0.92,
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      if (tickRef.current === 32) {
        onMessage({
          type: 'command_result',
          payload: {
            status: 'confirmation',
            command_type: 'engage',
            vehicle_callsign: 'UAV-1',
            message: 'CRITICAL RISK. Engaging hostile target. Say CONFIRM or CANCEL.',
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
        onMessage({
          type: 'confirmation_required',
          payload: {
            command_id: crypto.randomUUID(),
            command_type: 'engage',
            vehicle_callsign: 'UAV-1',
            risk_level: 'critical',
            readback_text: 'CONFIRM: CRITICAL RISK. You are ordering UAV-1 to ENGAGE hostile target. Say CONFIRM to execute or CANCEL to abort.',
          },
          timestamp: new Date().toISOString(),
        });
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [enabled, onMessage, onStatus]);
}
