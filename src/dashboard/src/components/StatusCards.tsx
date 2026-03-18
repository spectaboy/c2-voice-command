import type { VehicleStatus } from '../types';
import { AFFILIATION_LABELS } from '../types';

interface Props {
  vehicles: Map<string, VehicleStatus>;
}

function StatusCard({ vehicle }: { vehicle: VehicleStatus }) {
  const affClass =
    vehicle.affiliation === 'h' ? 'hostile' :
    vehicle.affiliation === 'u' ? 'unknown' :
    vehicle.affiliation === 'n' ? 'neutral' : '';

  return (
    <div className={`status-card ${affClass}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="callsign">{vehicle.callsign}</span>
        <span className={`armed-badge ${vehicle.armed ? 'armed' : 'disarmed'}`}>
          {vehicle.armed ? 'ARMED' : 'SAFE'}
        </span>
      </div>
      <div className="stat-row">
        <span>MODE</span>
        <span className="value">{vehicle.mode}</span>
      </div>
      <div className="stat-row">
        <span>AFFIL</span>
        <span className="value">{AFFILIATION_LABELS[vehicle.affiliation]}</span>
      </div>
      <div className="stat-row">
        <span>SPD</span>
        <span className="value">{vehicle.speed_mps.toFixed(1)} m/s</span>
      </div>
      <div className="stat-row">
        <span>HDG</span>
        <span className="value">{vehicle.heading.toFixed(0)}&deg;</span>
      </div>
      <div className="stat-row">
        <span>ALT</span>
        <span className="value">{vehicle.alt_m.toFixed(1)} m</span>
      </div>
      <div className="stat-row">
        <span>BAT</span>
        <span className="value">{vehicle.battery_pct.toFixed(0)}%</span>
      </div>
    </div>
  );
}

export default function StatusCards({ vehicles }: Props) {
  const sorted = Array.from(vehicles.values()).sort((a, b) =>
    a.callsign.localeCompare(b.callsign),
  );

  return (
    <div className="panel">
      <div className="panel-header">VEHICLE STATUS</div>
      <div className="panel-body">
        {sorted.length === 0 ? (
          <div className="empty-state">AWAITING VEHICLE DATA</div>
        ) : (
          <div className="status-cards">
            {sorted.map((v) => (
              <StatusCard key={v.uid} vehicle={v} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
