import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ConfirmationModal from '../../components/ConfirmationModal';
import type { ConfirmationRequest } from '../../types';

const mockRequest: ConfirmationRequest = {
  command_id: 'cmd-456',
  command_type: 'engage',
  vehicle_callsign: 'UAV-2',
  risk_level: 'critical',
  readback_text: 'CONFIRM: CRITICAL RISK. You are ordering UAV-2 to engage HOSTILE contact.',
};

describe('ConfirmationModal', () => {
  it('renders readback text', () => {
    render(<ConfirmationModal request={mockRequest} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText(/CRITICAL RISK/)).toBeInTheDocument();
    expect(screen.getByText(/UAV-2 to engage HOSTILE/)).toBeInTheDocument();
  });

  it('renders risk badge', () => {
    render(<ConfirmationModal request={mockRequest} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText('critical RISK')).toBeInTheDocument();
  });

  it('calls onConfirm when CONFIRM clicked', () => {
    const onConfirm = vi.fn();
    render(<ConfirmationModal request={mockRequest} onConfirm={onConfirm} onCancel={() => {}} />);
    fireEvent.click(screen.getByText('CONFIRM'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when CANCEL clicked', () => {
    const onCancel = vi.fn();
    render(<ConfirmationModal request={mockRequest} onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByText('CANCEL'));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
