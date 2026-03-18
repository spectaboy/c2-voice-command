import { Marker, Popup, Polyline } from 'react-leaflet';
import L from 'leaflet';
import type { VehicleStatus } from '../../types';
import { AFFILIATION_COLORS, AFFILIATION_LABELS } from '../../types';

// SVG shapes by domain
function markerSVG(domain: string, affiliation: string, heading: number): string {
  const color = AFFILIATION_COLORS[affiliation] ?? AFFILIATION_COLORS.u;
  const rotate = `rotate(${heading} 16 16)`;

  switch (domain) {
    case 'air':
      // Diamond
      return `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <g transform="${rotate}">
          <polygon points="16,2 30,16 16,30 2,16" fill="${color}" fill-opacity="0.3" stroke="${color}" stroke-width="2"/>
        </g>
      </svg>`;
    case 'ground':
      // Rectangle
      return `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <g transform="${rotate}">
          <rect x="4" y="8" width="24" height="16" fill="${color}" fill-opacity="0.3" stroke="${color}" stroke-width="2"/>
        </g>
      </svg>`;
    case 'maritime':
      // Lozenge (horizontal diamond / ellipse-like)
      return `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <g transform="${rotate}">
          <ellipse cx="16" cy="16" rx="14" ry="8" fill="${color}" fill-opacity="0.3" stroke="${color}" stroke-width="2"/>
        </g>
      </svg>`;
    default:
      return `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <circle cx="16" cy="16" r="12" fill="${color}" fill-opacity="0.3" stroke="${color}" stroke-width="2"/>
      </svg>`;
  }
}

function createIcon(vehicle: VehicleStatus): L.DivIcon {
  const svg = markerSVG(vehicle.domain, vehicle.affiliation, vehicle.heading);
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

interface Props {
  vehicle: VehicleStatus;
  trail: [number, number][];
}

export default function VehicleMarkerComponent({ vehicle, trail }: Props) {
  const color = AFFILIATION_COLORS[vehicle.affiliation] ?? AFFILIATION_COLORS.u;

  return (
    <>
      {trail.length > 1 && (
        <Polyline
          positions={trail.map(([lat, lon]) => [lat, lon])}
          pathOptions={{ color, weight: 1, opacity: 0.4, dashArray: '4 4' }}
        />
      )}
      <Marker
        position={[vehicle.lat, vehicle.lon]}
        icon={createIcon(vehicle)}
      >
        <Popup>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6 }}>
            <strong style={{ fontSize: 14 }}>{vehicle.callsign}</strong>
            <br />
            <span style={{ color }}>{AFFILIATION_LABELS[vehicle.affiliation]}</span> | {vehicle.domain.toUpperCase()}
            <hr style={{ border: 'none', borderTop: '1px solid #333', margin: '4px 0' }} />
            <b>MODE:</b> {vehicle.mode}<br />
            <b>SPD:</b> {vehicle.speed_mps.toFixed(1)} m/s<br />
            <b>HDG:</b> {vehicle.heading.toFixed(0)}&deg;<br />
            <b>ALT:</b> {vehicle.alt_m.toFixed(1)} m<br />
            <b>BAT:</b> {vehicle.battery_pct.toFixed(0)}%<br />
            <b>ARMED:</b> {vehicle.armed ? 'YES' : 'NO'}
          </div>
        </Popup>
      </Marker>
    </>
  );
}
