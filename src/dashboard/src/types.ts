// Mirror of Python schemas from CLAUDE.md

export interface VehicleStatus {
  uid: string;           // e.g. "SITL-UAV-01"
  callsign: string;      // e.g. "UAV-1"
  domain: 'air' | 'ground' | 'maritime';
  affiliation: 'f' | 'h' | 'u' | 'n'; // friendly | hostile | unknown | neutral
  lat: number;
  lon: number;
  alt_m: number;
  heading: number;       // 0-360
  speed_mps: number;
  battery_pct: number;   // 0-100
  mode: string;          // GUIDED, AUTO, RTL, LOITER, etc.
  armed: boolean;
}

export interface IFFAssessment {
  uid: string;
  affiliation: 'f' | 'h' | 'u' | 'n';
  confidence: number;    // 0.0-1.0
  threat_score: number;  // 0.0-1.0
  indicators: string[];  // e.g. ["intercept_course", "closing_speed"]
  timestamp: string;     // ISO 8601
}

export interface MilitaryCommand {
  command_id: string;
  command_type: string;  // move | rtb | loiter | patrol | overwatch | engage | classify | status
  vehicle_callsign: string;
  domain: 'air' | 'ground' | 'maritime';
  location?: {
    lat: number;
    lon: number;
    alt_m: number;
    grid_ref?: string;
  };
  parameters: Record<string, unknown>;
  raw_transcript: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  requires_confirmation: boolean;
  timestamp: string;
}

export interface CommandAck {
  command_id: string;
  status: 'acknowledged' | 'executing' | 'completed' | 'failed';
  vehicle_callsign: string;
  timestamp: string;
}

export interface VoiceTranscript {
  raw_transcript: string;
  confidence: number;    // 0.0-1.0
  parsed_command?: MilitaryCommand;
  timestamp: string;
}

export interface ConfirmationRequest {
  command_id: string;
  command_type: string;
  vehicle_callsign: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  readback_text: string;
}

export interface IFFAuditEntry {
  uid: string;
  callsign: string;
  previous_affiliation: 'f' | 'h' | 'u' | 'n';
  new_affiliation: 'f' | 'h' | 'u' | 'n';
  threat_score: number;
  indicators: string[];
  timestamp: string;
}

export type WSMessageType =
  | 'position_update'
  | 'iff_change'
  | 'command_ack'
  | 'voice_transcript'
  | 'confirmation_required';

export interface WSMessage {
  type: WSMessageType;
  payload: Record<string, unknown>;
  timestamp: string;
}

// Application state
export interface AppState {
  vehicles: Map<string, VehicleStatus>;
  trails: Map<string, [number, number][]>;
  transcripts: VoiceTranscript[];
  iffAuditLog: IFFAuditEntry[];
  pendingConfirmation: ConfirmationRequest | null;
  commandAcks: Map<string, CommandAck>;
  connectionStatus: 'connected' | 'reconnecting' | 'disconnected';
}

// Affiliation color mapping
export const AFFILIATION_COLORS: Record<string, string> = {
  f: '#00ff88', // friendly — green
  h: '#ff3333', // hostile — red
  u: '#ffff00', // unknown — yellow
  n: '#00aaff', // neutral — blue
};

export const AFFILIATION_LABELS: Record<string, string> = {
  f: 'FRIENDLY',
  h: 'HOSTILE',
  u: 'UNKNOWN',
  n: 'NEUTRAL',
};

export const MAX_TRAIL_LENGTH = 30;
