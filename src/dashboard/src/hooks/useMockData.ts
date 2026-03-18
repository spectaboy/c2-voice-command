import { useEffect, useRef } from 'react';
import type { WSMessage, AppState } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type StatusHandler = (status: AppState['connectionStatus']) => void;

// 6 vehicles: 3 UAV, 2 UGV, 1 USV
const MOCK_VEHICLES = [
  { uid: 'SITL-UAV-01', callsign: 'UAV-1', domain: 'air' as const, lat: 45.3170, lon: -75.6700, alt_m: 100, heading: 90 },
  { uid: 'SITL-UAV-02', callsign: 'UAV-2', domain: 'air' as const, lat: 45.3190, lon: -75.6650, alt_m: 120, heading: 180 },
  { uid: 'SITL-UAV-03', callsign: 'UAV-3', domain: 'air' as const, lat: 45.3140, lon: -75.6680, alt_m: 80, heading: 270 },
  { uid: 'SITL-UGV-01', callsign: 'UGV-1', domain: 'ground' as const, lat: 45.3130, lon: -75.6730, alt_m: 0, heading: 45 },
  { uid: 'SITL-UGV-02', callsign: 'UGV-2', domain: 'ground' as const, lat: 45.3120, lon: -75.6760, alt_m: 0, heading: 315 },
  { uid: 'SITL-USV-01', callsign: 'USV-1', domain: 'maritime' as const, lat: 45.3100, lon: -75.6800, alt_m: 0, heading: 135 },
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
        const msg: WSMessage = {
          type: 'position_update',
          payload: {
            uid: v.uid,
            callsign: v.callsign,
            domain: v.domain,
            affiliation: 'f',
            lat: v.lat + Math.sin(drift + MOCK_VEHICLES.indexOf(v)) * 0.002,
            lon: v.lon + Math.cos(drift + MOCK_VEHICLES.indexOf(v)) * 0.002,
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

      // Occasional voice transcript
      if (tickRef.current % 8 === 0) {
        onMessage({
          type: 'voice_transcript',
          payload: {
            raw_transcript: 'Alpha UAV proceed to waypoint bravo',
            confidence: jitter(0.92, 0.1),
            parsed_command: {
              command_id: crypto.randomUUID(),
              command_type: 'move',
              vehicle_callsign: 'UAV-1',
              domain: 'air',
              location: { lat: 45.318, lon: -75.670, alt_m: 100 },
              parameters: {},
              raw_transcript: 'Alpha UAV proceed to waypoint bravo',
              risk_level: 'low',
              requires_confirmation: false,
              timestamp: new Date().toISOString(),
            },
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Occasional IFF event
      if (tickRef.current === 15) {
        onMessage({
          type: 'iff_change',
          payload: {
            uid: 'SITL-UAV-03',
            affiliation: 'h',
            confidence: 0.85,
            threat_score: 0.78,
            indicators: ['intercept_course', 'high_speed_anomaly'],
            timestamp: new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Trigger confirmation modal once
      if (tickRef.current === 25) {
        onMessage({
          type: 'confirmation_required',
          payload: {
            command_id: crypto.randomUUID(),
            command_type: 'engage',
            vehicle_callsign: 'UAV-2',
            risk_level: 'critical',
            readback_text: 'CONFIRM: CRITICAL RISK. You are ordering UAV-2 to engage HOSTILE contact alpha-seven. Say CONFIRM to execute or CANCEL to abort.',
          },
          timestamp: new Date().toISOString(),
        });
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [enabled, onMessage, onStatus]);
}
