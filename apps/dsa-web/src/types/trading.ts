/**
 * Trading API type definitions
 * Mirrors api/v1/schemas/trading.py
 */

// ============ System & Account ============

export interface SystemStatus {
  trading_mode: string;
  tiger_connected: boolean;
  market_status: string;
}

export interface AccountSummary {
  net_value: number;
  cash: number;
  buying_power: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  market_value: number;
  pnl_pct: number;
}

// ============ Orders ============

export interface OrderInfo {
  order_id: string;
  symbol: string;
  action: string;
  quantity: number;
  filled: number;
  price: number;
  status: string;
}

// ============ Signals ============

export interface SignalInfo {
  signal_id: string;
  symbol: string;
  action: string;
  quantity: number | null;
  price_target: number | null;
  confidence: number;
  status: string;
  created_at: string;
  rationale: string;
}

export interface SignalCreateRequest {
  symbol: string;
  action: string;
  quantity?: number;
  confidence?: number;
  rationale?: string;
}

// ============ Risk & Strategy ============

export interface RiskConfig {
  max_position_pct: number;
  max_daily_loss_pct: number;
  max_order_value: number;
  max_orders_per_min: number;
  max_daily_orders: number;
  signal_ttl_minutes: number;
}

export interface StrategyInfo {
  name: string;
  class_name: string;
  enabled: boolean;
}

// ============ Bridge ============

export interface BridgeStatus {
  enabled: boolean;
  running: boolean;
  poll_interval_sec: number;
  min_confidence: number;
  max_age_sec: number;
  allowed_source_types: string[];
  allowed_actions: string[];
  last_run: string | null;
  last_result: {
    polled: number;
    accepted: number;
    rejected: number;
    errors: number;
  } | null;
}
