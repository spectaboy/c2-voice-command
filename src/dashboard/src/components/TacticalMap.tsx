import { MapContainer, TileLayer } from 'react-leaflet';
import type { VehicleStatus } from '../types';
import VehicleMarkerComponent from './markers/VehicleMarker';

// SITL default area — Halifax Harbor
const DEFAULT_CENTER: [number, number] = [44.6488, -63.5752];
const DEFAULT_ZOOM = 14;

interface Props {
  vehicles: Map<string, VehicleStatus>;
  trails: Map<string, [number, number][]>;
}

export default function TacticalMap({ vehicles, trails }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">TACTICAL MAP</div>
      <div style={{ flex: 1 }}>
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          zoomControl={false}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {Array.from(vehicles.values()).map((v) => (
            <VehicleMarkerComponent
              key={v.uid}
              vehicle={v}
              trail={trails.get(v.uid) ?? []}
            />
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
