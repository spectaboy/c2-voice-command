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
  | { type: 'set_connection'; status: AppState['connectionStatus'] };

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
