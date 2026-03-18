import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusCards from '../../components/StatusCards';
import type { VehicleStatus } from '../../types';

function makeVehicle(overrides: Partial<VehicleStatus> = {}): VehicleStatus {
  return {
    uid: 'SITL-UAV-01',
    callsign: 'UAV-1',
    domain: 'air',
    affiliation: 'f',
    lat: 45.0,
    lon: -75.0,
    alt_m: 100,
    heading: 90,
    speed_mps: 12.5,
    battery_pct: 85,
    mode: 'GUIDED',
    armed: true,
    ...overrides,
  };
}

describe('StatusCards', () => {
  it('shows empty state when no vehicles', () => {
    render(<StatusCards vehicles={new Map()} />);
    expect(screen.getByText('AWAITING VEHICLE DATA')).toBeInTheDocument();
  });

  it('renders a vehicle card with callsign', () => {
    const vehicles = new Map([['UAV-1', makeVehicle()]]);
    render(<StatusCards vehicles={vehicles} />);
    expect(screen.getByText('UAV-1')).toBeInTheDocument();
  });

  it('shows ARMED badge when armed', () => {
    const vehicles = new Map([['UAV-1', makeVehicle({ armed: true })]]);
    render(<StatusCards vehicles={vehicles} />);
    expect(screen.getByText('ARMED')).toBeInTheDocument();
  });

  it('shows SAFE badge when disarmed', () => {
    const vehicles = new Map([['UAV-1', makeVehicle({ armed: false })]]);
    render(<StatusCards vehicles={vehicles} />);
    expect(screen.getByText('SAFE')).toBeInTheDocument();
  });

  it('displays mode', () => {
    const vehicles = new Map([['UAV-1', makeVehicle({ mode: 'RTL' })]]);
    render(<StatusCards vehicles={vehicles} />);
    expect(screen.getByText('RTL')).toBeInTheDocument();
  });

  it('renders multiple vehicles sorted by callsign', () => {
    const vehicles = new Map([
      ['UGV-1', makeVehicle({ uid: 'UGV-1', callsign: 'UGV-1', domain: 'ground' })],
      ['UAV-1', makeVehicle({ uid: 'UAV-1', callsign: 'UAV-1', domain: 'air' })],
    ]);
    render(<StatusCards vehicles={vehicles} />);
    const cards = screen.getAllByText(/UAV-1|UGV-1/);
    expect(cards[0].textContent).toBe('UAV-1');
    expect(cards[1].textContent).toBe('UGV-1');
  });
});
