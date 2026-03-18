import type { ConfirmationRequest } from '../types';

interface Props {
  request: ConfirmationRequest;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmationModal({ request, onConfirm, onCancel }: Props) {
  return (
    <div className="confirmation-overlay">
      <div className="confirmation-modal">
        <div className={`risk-badge ${request.risk_level}`}>
          {request.risk_level} RISK
        </div>
        <div style={{ fontSize: 11, color: '#6e7a86', textTransform: 'uppercase', letterSpacing: 2 }}>
          {request.command_type} — {request.vehicle_callsign}
        </div>
        <div className="readback">{request.readback_text}</div>
        <div className="btn-row">
          <button className="btn-cancel" onClick={onCancel}>CANCEL</button>
          <button className="btn-confirm" onClick={onConfirm}>CONFIRM</button>
        </div>
      </div>
    </div>
  );
}
