import { useCallback } from 'react';
import { useAppState } from './hooks/useAppState';
import { useWebSocket } from './hooks/useWebSocket';
import { useMockData } from './hooks/useMockData';
import ClassificationBanner from './components/ClassificationBanner';
import TacticalMap from './components/TacticalMap';
import StatusCards from './components/StatusCards';
import TranscriptLog from './components/TranscriptLog';
import IFFAuditTrail from './components/IFFAuditTrail';
import ConfirmationModal from './components/ConfirmationModal';

const WS_URL = `ws://${window.location.hostname}:8005/ws`;
const isMock = new URLSearchParams(window.location.search).has('mock');

export default function App() {
  const { state, handleWSMessage, setConnectionStatus, dismissConfirmation } = useAppState();

  useWebSocket(
    isMock ? 'ws://localhost:0' : WS_URL, // dummy URL in mock mode
    handleWSMessage,
    setConnectionStatus,
  );

  useMockData(isMock, handleWSMessage, setConnectionStatus);

  const handleConfirm = useCallback(async () => {
    if (!state.pendingConfirmation) return;
    try {
      await fetch(`/confirm/${state.pendingConfirmation.command_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'confirm' }),
      });
    } catch {
      // coordinator may be offline
    }
    dismissConfirmation();
  }, [state.pendingConfirmation, dismissConfirmation]);

  const handleCancel = useCallback(async () => {
    if (!state.pendingConfirmation) return;
    try {
      await fetch(`/confirm/${state.pendingConfirmation.command_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' }),
      });
    } catch {
      // coordinator may be offline
    }
    dismissConfirmation();
  }, [state.pendingConfirmation, dismissConfirmation]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ClassificationBanner />

      <div className="header-bar">
        <span>C2 TACTICAL DASHBOARD</span>
        <div className="connection-status">
          <div className={`connection-dot ${state.connectionStatus}`} />
          <span>{isMock ? 'MOCK' : state.connectionStatus.toUpperCase()}</span>
        </div>
      </div>

      <div className="dashboard-grid" style={{ flex: 1 }}>
        <TacticalMap vehicles={state.vehicles} trails={state.trails} />
        <StatusCards vehicles={state.vehicles} />
        <TranscriptLog transcripts={state.transcripts} />
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <IFFAuditTrail entries={state.iffAuditLog} />
        </div>
      </div>

      <ClassificationBanner />

      {state.pendingConfirmation && (
        <ConfirmationModal
          request={state.pendingConfirmation}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </div>
  );
}
