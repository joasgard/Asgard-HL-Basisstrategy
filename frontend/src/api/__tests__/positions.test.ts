import { describe, it, expect, vi, beforeEach } from 'vitest';
import { positionsApi } from '../positions';
import apiClient from '../client';

vi.mock('../client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('positionsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should list positions', async () => {
    const mockPositions = [
      { id: 'pos_1', asset: 'SOL', status: 'open' },
      { id: 'pos_2', asset: 'ETH', status: 'closed' },
    ];
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockPositions });

    const result = await positionsApi.list();

    expect(apiClient.get).toHaveBeenCalledWith('/positions');
    expect(result).toEqual(mockPositions);
  });

  it('should get single position', async () => {
    const mockPosition = { id: 'pos_1', asset: 'SOL', status: 'open' };
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockPosition });

    const result = await positionsApi.get('pos_1');

    expect(apiClient.get).toHaveBeenCalledWith('/positions/pos_1');
    expect(result).toEqual(mockPosition);
  });

  it('should open position', async () => {
    const mockResponse = { job_id: 'job_123' };
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockResponse });

    const result = await positionsApi.open({
      asset: 'SOL',
      leverage: 3.0,
      size_usd: 5000,
    });

    expect(apiClient.post).toHaveBeenCalledWith('/positions/open', {
      asset: 'SOL',
      leverage: 3.0,
      size_usd: 5000,
    });
    expect(result).toEqual(mockResponse);
  });

  it('should close position', async () => {
    const mockResponse = { job_id: 'job_456' };
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockResponse });

    const result = await positionsApi.close('pos_1');

    expect(apiClient.post).toHaveBeenCalledWith('/positions/pos_1/close');
    expect(result).toEqual(mockResponse);
  });

  it('should get job status', async () => {
    const mockStatus = {
      job_id: 'job_123',
      status: 'completed' as const,
      position_id: 'pos_123',
    };
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: mockStatus });

    const result = await positionsApi.getJobStatus('job_123');

    expect(apiClient.get).toHaveBeenCalledWith('/positions/jobs/job_123');
    expect(result).toEqual(mockStatus);
  });
});
