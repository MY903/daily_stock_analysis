import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  SystemStatus,
  AccountSummary,
  Position,
  OrderInfo,
  SignalInfo,
  SignalCreateRequest,
  RiskConfig,
  StrategyInfo,
} from '../types/trading';

// ============ API ============

export const tradingApi = {
  /**
   * Get trading system status (mode, Tiger connection, market status)
   */
  getStatus: async (): Promise<SystemStatus> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/trading/status');
    return toCamelCase<SystemStatus>(response.data);
  },

  /**
   * Get account summary (net value, cash, buying power)
   */
  getAccount: async (): Promise<AccountSummary> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/trading/account');
    return toCamelCase<AccountSummary>(response.data);
  },

  /**
   * Get current open positions
   */
  getPositions: async (): Promise<Position[]> => {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/trading/positions');
    return (response.data || []).map((item) => toCamelCase<Position>(item));
  },

  /**
   * Get orders
   */
  getOrders: async (): Promise<OrderInfo[]> => {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/trading/orders');
    return (response.data || []).map((item) => toCamelCase<OrderInfo>(item));
  },

  /**
   * Create a new trading signal
   */
  createSignal: async (data: SignalCreateRequest): Promise<SignalInfo> => {
    const requestData: Record<string, unknown> = { symbol: data.symbol, action: data.action };
    if (data.quantity != null) requestData.quantity = data.quantity;
    if (data.confidence != null) requestData.confidence = data.confidence;
    if (data.rationale) requestData.rationale = data.rationale;

    const response = await apiClient.post<Record<string, unknown>>('/api/v1/trading/signals', requestData);
    return toCamelCase<SignalInfo>(response.data);
  },

  /**
   * Get trading signals with optional filters
   */
  getSignals: async (params: {
    status?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<SignalInfo[]> => {
    const queryParams: Record<string, string | number> = {};
    if (params.status) queryParams.status = params.status;
    if (params.limit != null) queryParams.limit = params.limit;
    if (params.offset != null) queryParams.offset = params.offset;

    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/trading/signals', { params: queryParams });
    return (response.data || []).map((item) => toCamelCase<SignalInfo>(item));
  },

  /**
   * Confirm a signal (promote to order)
   */
  confirmSignal: async (signalId: string): Promise<SignalInfo> => {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/trading/signals/${encodeURIComponent(signalId)}/confirm`);
    return toCamelCase<SignalInfo>(response.data);
  },

  /**
   * Reject a signal
   */
  rejectSignal: async (signalId: string): Promise<SignalInfo> => {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/trading/signals/${encodeURIComponent(signalId)}/reject`);
    return toCamelCase<SignalInfo>(response.data);
  },

  /**
   * Get risk configuration
   */
  getRiskConfig: async (): Promise<RiskConfig> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/trading/risk-config');
    return toCamelCase<RiskConfig>(response.data);
  },

  /**
   * Get strategy list
   */
  getStrategies: async (): Promise<StrategyInfo[]> => {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/trading/strategies');
    return (response.data || []).map((item) => toCamelCase<StrategyInfo>(item));
  },
};
