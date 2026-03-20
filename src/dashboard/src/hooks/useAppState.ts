import { useReducer, useCallback } from 'react';
import type {
  AppState,
  WSMessage,
  VehicleStatus,
  IFFAssessment,
  CommandAck,
  VoiceTranscript,
  ConfirmationRequest,
  IFFAuditEntry,
} from '../types';
import { MAX_TRAIL_LENGTH } from '../types';

// --- Actions ---

type Action =
  | { type: 'position_update'; payload: VehicleStatus }
  | { type: 'iff_change'; payload: IFFAssessment }
  | { type: 'command_ack'; payload: CommandAck }
  | { type: 'voice_transcript'; payload: VoiceTranscript }
  | { type: 'confirmation_required'; payload: ConfirmationRequest }
  | { type: 'dismiss_confirmation' }
  | { type: 'set_connection'; status: AppState['connectionStatus'] }
  | { type: 'command_result'; payload: { status: string; command_type: string; vehicle_callsign: string; message: string; timestamp: string } }
  | { type: 'command_error'; payload: { message: string; timestamp?: string } };

// --- Initial state ---

const initialState: AppState = {
  vehicles: new Map(),
  trails: new Map(),
  transcripts: [],
  iffAuditLog: [],
  pendingConfirmation: null,
  commandAcks: new Map(),
  connectionStatus: 'disconnected',
};

// --- Reducer ---

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'position_update': {
      const v = action.payload;
      const vehicles = new Map(state.vehicles);
      vehicles.set(v.uid, v);

      const trails = new Map(state.trails);
      const trail = [...(trails.get(v.uid) ?? []), [v.lat, v.lon] as [number, number]];
      if (trail.length > MAX_TRAIL_LENGTH) trail.shift();
      trails.set(v.uid, trail);

      return { ...state, vehicles, trails };
    }

    case 'iff_change': {
      const iff = action.payload;
      const vehicles = new Map(state.vehicles);
      const existing = vehicles.get(iff.uid);

      const entry: IFFAuditEntry = {
        uid: iff.uid,
        callsign: existing?.callsign ?? iff.uid,
        previous_affiliation: existing?.affiliation ?? 'u',
        new_affiliation: iff.affiliation,
        threat_score: iff.threat_score,
        indicators: iff.indicators,
        timestamp: iff.timestamp,
      };

      if (existing) {
        vehicles.set(iff.uid, { ...existing, affiliation: iff.affiliation });
      }

      return {
        ...state,
        vehicles,
        iffAuditLog: [...state.iffAuditLog, entry],
      };
    }

    case 'command_ack': {
      const ack = action.payload;
      const commandAcks = new Map(state.commandAcks);
      commandAcks.set(ack.command_id, ack);
      return { ...state, commandAcks };
    }

    case 'command_result': {
      const p = action.payload;
      const entry: VoiceTranscript = {
        raw_transcript: p.message,
        confidence: 1.0,
        timestamp: p.timestamp || new Date().toISOString(),
        status: p.status as VoiceTranscript['status'],
        status_message: p.message,
        command_type: p.command_type,
        vehicle_callsign: p.vehicle_callsign,
      };
      return { ...state, transcripts: [...state.transcripts, entry] };
    }

    case 'command_error': {
      const p = action.payload;
      const entry: VoiceTranscript = {
        raw_transcript: p.message,
        confidence: 0,
        timestamp: p.timestamp || new Date().toISOString(),
        status: 'error',
        status_message: p.message,
      };
      return { ...state, transcripts: [...state.transcripts, entry] };
    }

    case 'voice_transcript': {
      return {
        ...state,
        transcripts: [...state.transcripts, action.payload],
      };
    }

    case 'confirmation_required': {
      return { ...state, pendingConfirmation: action.payload };
    }

    case 'dismiss_confirmation': {
      return { ...state, pendingConfirmation: null };
    }

    case 'set_connection': {
      return { ...state, connectionStatus: action.status };
    }

    default:
      return state;
  }
}

// --- Hook ---

export function useAppState() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    const { type, payload } = msg;
    switch (type) {
      case 'position_update':
        dispatch({ type: 'position_update', payload: payload as unknown as VehicleStatus });
        break;
      case 'iff_change':
        dispatch({ type: 'iff_change', payload: payload as unknown as IFFAssessment });
        break;
      case 'command_ack':
        dispatch({ type: 'command_ack', payload: payload as unknown as CommandAck });
        break;
      case 'voice_transcript':
        dispatch({ type: 'voice_transcript', payload: payload as unknown as VoiceTranscript });
        break;
      case 'confirmation_required':
        dispatch({ type: 'confirmation_required', payload: payload as unknown as ConfirmationRequest });
        break;
      case 'command_result':
        dispatch({ type: 'command_result', payload: payload as unknown as { status: string; command_type: string; vehicle_callsign: string; message: string; timestamp: string } });
        break;
      case 'command_error':
        dispatch({ type: 'command_error', payload: payload as unknown as { message: string; timestamp?: string } });
        break;
    }
  }, []);

  const setConnectionStatus = useCallback((status: AppState['connectionStatus']) => {
    dispatch({ type: 'set_connection', status });
  }, []);

  const dismissConfirmation = useCallback(() => {
    dispatch({ type: 'dismiss_confirmation' });
  }, []);

  return { state, handleWSMessage, setConnectionStatus, dismissConfirmation };
}
