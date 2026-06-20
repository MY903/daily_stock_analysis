import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle,
  DollarSign,
  PieChart,
  RefreshCw,
  Shield,
  TrendingUp,
  Wallet,
  XCircle,
} from 'lucide-react';
import { tradingApi } from '../api/trading';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  Badge,
  Card,
  EmptyState,
  Loading,
  Pagination,
  StatCard,
} from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { cn } from '../utils/cn';
import { TRADING_TEXT } from '../locales/featureText';
import type {
  AccountSummary,
  OrderInfo,
  BridgeStatus,
  Position,
  RiskConfig,
  SignalInfo,
  StrategyInfo,
  SystemStatus,
} from '../types/trading';

type TabKey = 'overview' | 'trade' | 'history';

const SIGNAL_PAGE_SIZE = 15;

// ============ Helpers ============

function modeBadge(mode: string, language: 'zh' | 'en') {
  const text = TRADING_TEXT[language];
  switch (mode.toLowerCase()) {
    case 'sandbox':
      return <Badge variant="warning">{text.sandbox}</Badge>;
    case 'paper':
      return <Badge variant="info">{text.paper}</Badge>;
    case 'prod':
      return <Badge variant="success" glow>{text.prod}</Badge>;
    default:
      return <Badge variant="default">{mode}</Badge>;
  }
}

function statusBadge(status: string, language: 'zh' | 'en') {
  const text = TRADING_TEXT[language];
  switch (status) {
    case 'pending':
      return <Badge variant="warning">{text.pending}</Badge>;
    case 'confirmed':
      return <Badge variant="success">{text.confirmed}</Badge>;
    case 'rejected':
      return <Badge variant="danger">{text.rejected}</Badge>;
    case 'expired':
      return <Badge variant="default">{text.expired}</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
}

function orderStatusBadge(status: string) {
  switch (status.toLowerCase()) {
    case 'filled':
      return <Badge variant="success">Filled</Badge>;
    case 'partial':
      return <Badge variant="warning">Partial</Badge>;
    case 'pending':
    case 'submitted':
      return <Badge variant="info">Pending</Badge>;
    case 'cancelled':
      return <Badge variant="default">Cancelled</Badge>;
    case 'rejected':
      return <Badge variant="danger">Rejected</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(2)}`;
}

function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function formatTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString();
  } catch {
    return isoString;
  }
}

// ============ Tabs ============

const TABS: Array<{ key: TabKey; labelKey: keyof typeof TRADING_TEXT.zh; icon: React.ReactNode }> = [
  { key: 'overview', labelKey: 'overview', icon: <Activity className="h-4 w-4" /> },
  { key: 'trade', labelKey: 'trade', icon: <TrendingUp className="h-4 w-4" /> },
  { key: 'history', labelKey: 'history', icon: <PieChart className="h-4 w-4" /> },
];

// ============ Main Page ============

const TradingPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const text = TRADING_TEXT[language];

  // Set page title
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  // Tab state
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // Overview state
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [riskConfig, setRiskConfig] = useState<RiskConfig | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus | null>(null);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<ParsedApiError | null>(null);

  // Trade state
  const [symbol, setSymbol] = useState('');
  const [signalAction, setSignalAction] = useState('BUY');
  const [quantity, setQuantity] = useState('');
  const [confidence, setConfidence] = useState('');
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [signalResult, setSignalResult] = useState<SignalInfo | null>(null);
  const [signalError, setSignalError] = useState<ParsedApiError | null>(null);

  // Pending signals state
  const [pendingSignals, setPendingSignals] = useState<SignalInfo[]>([]);
  const [pendingSignalsLoading, setPendingSignalsLoading] = useState(false);

  // Active orders state
  const [orders, setOrders] = useState<OrderInfo[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  // History state
  const [historySignals, setHistorySignals] = useState<SignalInfo[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyStatusFilter, setHistoryStatusFilter] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);

  // Confirm/reject state
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);

  // ============ Overview data fetching ============

  const fetchOverview = useCallback(async () => {
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const [statusData, accountData, positionsData, riskData, strategiesData, bridgeData] = await Promise.all([
        tradingApi.getStatus(),
        tradingApi.getAccount(),
        tradingApi.getPositions(),
        tradingApi.getRiskConfig(),
        tradingApi.getStrategies(),
        tradingApi.getBridgeStatus(),
      ]);
      setStatus(statusData);
      setAccount(accountData);
      setPositions(positionsData);
      setRiskConfig(riskData);
      setStrategies(strategiesData);
      setBridgeStatus(bridgeData);
    } catch (err) {
      setOverviewError(getParsedApiError(err));
    } finally {
      setOverviewLoading(false);
    }
  }, []);

  // ============ Pending signals ============

  const fetchPendingSignals = useCallback(async () => {
    setPendingSignalsLoading(true);
    try {
      const data = await tradingApi.getSignals({ status: 'pending' });
      setPendingSignals(data);
    } catch {
      // Silently fail; shown via the overview error path
    } finally {
      setPendingSignalsLoading(false);
    }
  }, []);

  // ============ Active orders ============

  const fetchOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const data = await tradingApi.getOrders();
      setOrders(data);
    } catch {
      // Silently fail
    } finally {
      setOrdersLoading(false);
    }
  }, []);

  // ============ Signal history ============

  const fetchHistory = useCallback(async (page: number, statusFilter: string) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const params: { status?: string; limit: number; offset: number } = {
        limit: SIGNAL_PAGE_SIZE,
        offset: (page - 1) * SIGNAL_PAGE_SIZE,
      };
      if (statusFilter) params.status = statusFilter;
      const data = await tradingApi.getSignals(params);
      setHistorySignals(data);
      // Estimate total from returned count (API may not return total)
      setHistoryTotal(data.length < SIGNAL_PAGE_SIZE ? (page - 1) * SIGNAL_PAGE_SIZE + data.length : page * SIGNAL_PAGE_SIZE + SIGNAL_PAGE_SIZE);
    } catch (err) {
      setHistoryError(getParsedApiError(err));
      setHistorySignals([]);
      setHistoryTotal(0);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // ============ Initial loads ============

  useEffect(() => {
    void fetchOverview();
    void fetchPendingSignals();
    void fetchOrders();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (activeTab === 'history') {
      void fetchHistory(historyPage, historyStatusFilter);
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  // ============ Signal create ============

  const handleCreateSignal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim()) return;

    setSubmitting(true);
    setSignalResult(null);
    setSignalError(null);
    try {
      const result = await tradingApi.createSignal({
        symbol: symbol.trim().toUpperCase(),
        action: signalAction,
        quantity: quantity ? Number(quantity) : undefined,
        confidence: confidence ? Number(confidence) : undefined,
        rationale: rationale.trim() || undefined,
      });
      setSignalResult(result);
      // Reset form
      setQuantity('');
      setConfidence('');
      setRationale('');
      // Refresh pending signals
      void fetchPendingSignals();
    } catch (err) {
      setSignalError(getParsedApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  // ============ Confirm/Reject signals ============

  const handleConfirmSignal = async (signalId: string) => {
    setConfirmingId(signalId);
    try {
      await tradingApi.confirmSignal(signalId);
      void fetchPendingSignals();
      void fetchOrders();
    } catch {
      // Silently fail — refresh will show the original state
    } finally {
      setConfirmingId(null);
    }
  };

  const handleRejectSignal = async (signalId: string) => {
    setRejectingId(signalId);
    try {
      await tradingApi.rejectSignal(signalId);
      void fetchPendingSignals();
    } catch {
      // Silently fail
    } finally {
      setRejectingId(null);
    }
  };

  // ============ History pagination ============

  const handleHistoryFilter = (newStatus: string) => {
    setHistoryStatusFilter(newStatus);
    setHistoryPage(1);
    void fetchHistory(1, newStatus);
  };

  const handleHistoryPageChange = (page: number) => {
    setHistoryPage(page);
    void fetchHistory(page, historyStatusFilter);
  };

  const totalHistoryPages = Math.max(1, Math.ceil(historyTotal / SIGNAL_PAGE_SIZE));

  // ============ Render: Overview Tab ============

  const renderOverview = () => {
    if (overviewLoading) {
      return <Loading label={text.overviewLoading} />;
    }

    if (overviewError) {
      return (
        <ApiErrorAlert
          error={overviewError}
          actionLabel={t('common.retry')}
          onAction={() => void fetchOverview()}
        />
      );
    }

    return (
      <div className="space-y-5 animate-fade-in">
        {/* Asset cards */}
        {account ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label={text.netValue}
              value={formatCurrency(account.net_value)}
              icon={<DollarSign className="h-5 w-5" />}
              tone="primary"
            />
            <StatCard
              label={text.cash}
              value={formatCurrency(account.cash)}
              icon={<Wallet className="h-5 w-5" />}
              tone="success"
            />
            <StatCard
              label={text.buyingPower}
              value={formatCurrency(account.buying_power)}
              icon={<TrendingUp className="h-5 w-5" />}
              tone="warning"
            />
          </div>
        ) : null}

        {/* System status */}
        <Card padding="md">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              <Shield className="mr-2 inline-block h-4 w-4 text-cyan" />
              {text.modeLabel}
            </h3>
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 !text-xs"
              onClick={() => void fetchOverview()}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {t('common.retry')}
            </button>
          </div>
          {status ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">{text.modeLabel}</p>
                <div className="flex items-center gap-2">
                  {modeBadge(status.trading_mode, language)}
                  <span className="text-sm text-secondary-text">{status.trading_mode}</span>
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">{text.tigerConnected}</p>
                <div className="flex items-center gap-2">
                  {status.tiger_connected ? (
                    <>
                      <CheckCircle className="h-4 w-4 text-success" />
                      <span className="text-sm text-success">{text.tigerConnectedYes}</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 text-danger" />
                      <span className="text-sm text-danger">{text.tigerConnectedNo}</span>
                    </>
                  )}
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">{text.marketStatus}</p>
                <span className="text-sm text-foreground">{status.market_status}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-secondary-text">{text.loading}</p>
          )}
        </Card>

        {/* Signal bridge status */}
        <Card padding="md">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              <Activity className="mr-2 inline-block h-4 w-4 text-purple-500" />
              DecisionSignal Bridge
            </h3>
            <div className="flex items-center gap-2">
              {bridgeStatus ? (
                <button
                  type="button"
                  className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 !text-xs"
                  onClick={async () => {
                    try {
                      await tradingApi.triggerBridge();
                      await fetchOverview();
                    } catch { /* ignore */ }
                  }}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Trigger
                </button>
              ) : null}
            </div>
          </div>
          {bridgeStatus ? (
            <div className="grid gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">Enabled</p>
                {bridgeStatus.enabled ? (
                  <span className="text-sm text-success flex items-center gap-1"><CheckCircle className="h-3.5 w-3.5" /> Yes</span>
                ) : (
                  <span className="text-sm text-secondary-text flex items-center gap-1"><XCircle className="h-3.5 w-3.5" /> No</span>
                )}
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">Status</p>
                {bridgeStatus.running ? (
                  <span className="text-sm text-success">Running</span>
                ) : (
                  <span className="text-sm text-secondary-text">Idle</span>
                )}
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">Poll Interval</p>
                <span className="text-sm text-foreground">{bridgeStatus.pollIntervalSec}s</span>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-secondary-text mb-1">Last Run</p>
                <span className="text-sm text-foreground">{bridgeStatus.lastRun ? new Date(bridgeStatus.lastRun).toLocaleString() : "-"}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-secondary-text">Bridge not configured or API unavailable</p>
          )}
          {bridgeStatus?.lastResult ? (
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <div className="bg-gray-50 rounded p-2 text-center">
                <div className="text-lg font-semibold text-gray-700">{bridgeStatus.lastResult.polled}</div>
                <div className="text-xs text-gray-500">Polled</div>
              </div>
              <div className="bg-green-50 rounded p-2 text-center">
                <div className="text-lg font-semibold text-green-700">{bridgeStatus.lastResult.accepted}</div>
                <div className="text-xs text-green-600">Accepted</div>
              </div>
              <div className="bg-yellow-50 rounded p-2 text-center">
                <div className="text-lg font-semibold text-yellow-700">{bridgeStatus.lastResult.rejected}</div>
                <div className="text-xs text-yellow-600">Rejected</div>
              </div>
              <div className="bg-red-50 rounded p-2 text-center">
                <div className="text-lg font-semibold text-red-700">{bridgeStatus.lastResult.errors}</div>
                <div className="text-xs text-red-600">Errors</div>
              </div>
            </div>
          ) : null}
        </Card>

        {/* Positions */}
        <Card padding="md">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-foreground">{text.positions}</h3>
          </div>
          {positions.length === 0 ? (
            <EmptyState
              title={text.noPositions}
              className="border-none bg-transparent py-6 shadow-none"
              icon={<Activity className="h-5 w-5" />}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/40">
                    <th className="pb-2 pr-4 font-medium text-secondary-text">{t('trading.symbolCol') ?? text.symbolCol}</th>
                    <th className="pb-2 pr-4 font-medium text-secondary-text">{t('trading.quantityCol') ?? text.quantityCol}</th>
                    <th className="pb-2 pr-4 font-medium text-secondary-text">Avg Price</th>
                    <th className="pb-2 pr-4 font-medium text-secondary-text">Market Value</th>
                    <th className="pb-2 font-medium text-secondary-text">P&L %</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos, idx) => (
                    <tr key={`${pos.symbol}-${idx}`} className="border-b border-border/20 last:border-0">
                      <td className="py-2 pr-4 font-medium text-foreground">{pos.symbol}</td>
                      <td className="py-2 pr-4 text-secondary-text">{pos.quantity}</td>
                      <td className="py-2 pr-4 text-secondary-text">${pos.avg_price.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-secondary-text">${pos.market_value.toFixed(2)}</td>
                      <td className={cn('py-2 font-medium', pos.pnl_pct >= 0 ? 'text-success' : 'text-danger')}>
                        {formatPct(pos.pnl_pct)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Risk Config & Strategies */}
        <div className="grid gap-4 md:grid-cols-2">
          {riskConfig ? (
            <Card padding="md">
              <h3 className="mb-3 text-sm font-semibold text-foreground">{text.riskConfig}</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.maxPositionPct}</span>
                  <span className="font-mono text-foreground">{riskConfig.max_position_pct}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.maxDailyLossPct}</span>
                  <span className="font-mono text-foreground">{riskConfig.max_daily_loss_pct}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.maxOrderValue}</span>
                  <span className="font-mono text-foreground">{formatCurrency(riskConfig.max_order_value)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.maxOrdersPerMin}</span>
                  <span className="font-mono text-foreground">{riskConfig.max_orders_per_min}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.maxDailyOrders}</span>
                  <span className="font-mono text-foreground">{riskConfig.max_daily_orders}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-secondary-text">{text.signalTtlMinutes}</span>
                  <span className="font-mono text-foreground">{riskConfig.signal_ttl_minutes}</span>
                </div>
              </div>
            </Card>
          ) : null}

          {strategies.length > 0 ? (
            <Card padding="md">
              <h3 className="mb-3 text-sm font-semibold text-foreground">{text.strategies}</h3>
              <div className="space-y-2">
                {strategies.map((strategy) => (
                  <div key={strategy.name} className="flex items-center justify-between rounded-lg border border-border/30 bg-card/50 px-3 py-2">
                    <div>
                      <p className="text-sm font-medium text-foreground">{strategy.name}</p>
                      <p className="text-xs text-secondary-text font-mono">{strategy.class_name}</p>
                    </div>
                    {strategy.enabled ? (
                      <Badge variant="success" size="sm">{text.enabled}</Badge>
                    ) : (
                      <Badge variant="default" size="sm">{text.disabled}</Badge>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    );
  };

  // ============ Render: Trade Tab ============

  const renderTrade = () => (
    <div className="space-y-5 animate-fade-in">
      {/* Signal form */}
      <Card title={text.signalForm} padding="md">
        <form onSubmit={handleCreateSignal} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Symbol */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-foreground">{text.symbol}</label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder={text.symbolPlaceholder}
                required
                disabled={submitting}
                className="input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>

            {/* Action */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-foreground">{text.action}</label>
              <select
                value={signalAction}
                onChange={(e) => setSignalAction(e.target.value)}
                disabled={submitting}
                className="input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="BUY">{text.actionBuy}</option>
                <option value="SELL">{text.actionSell}</option>
                <option value="HOLD">{text.actionHold}</option>
              </select>
            </div>

            {/* Quantity */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-foreground">{text.quantity}</label>
              <input
                type="number"
                min={0}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder={text.quantityPlaceholder}
                disabled={submitting}
                className="input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>

            {/* Confidence */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-foreground">{text.confidence}</label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={confidence}
                onChange={(e) => setConfidence(e.target.value)}
                placeholder={text.confidencePlaceholder}
                disabled={submitting}
                className="input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>
          </div>

          {/* Rationale */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-foreground">{text.rationale}</label>
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder={text.rationalePlaceholder}
              rows={3}
              disabled={submitting}
              className="input-surface input-focus-glow w-full rounded-xl border bg-transparent px-4 py-2.5 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 resize-none"
            />
          </div>

          {/* Submit */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting || !symbol.trim()}
              className="btn-primary inline-flex items-center gap-2"
            >
              {submitting ? (
                <>
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  {text.submitting}
                </>
              ) : (
                text.submitSignal
              )}
            </button>
          </div>

          {/* Result feedback */}
          {signalResult && (
            <div className="rounded-xl border border-success/20 bg-success/10 px-4 py-3 text-sm text-success">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle className="h-4 w-4" />
                {text.signalSuccess}
              </div>
            </div>
          )}
          {signalError && (
            <ApiErrorAlert error={signalError} />
          )}
        </form>
      </Card>

      {/* Pending signals */}
      <Card padding="md">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-foreground">{text.pendingSignals}</h3>
        </div>
        {pendingSignalsLoading ? (
          <Loading />
        ) : pendingSignals.length === 0 ? (
          <EmptyState
            title={text.noPendingSignals}
            className="border-none bg-transparent py-6 shadow-none"
            icon={<Activity className="h-5 w-5" />}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.time}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.symbolCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.actionCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.quantityCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.confidenceCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.rationaleCol}</th>
                  <th className="pb-2 font-medium text-secondary-text">{t('trading.action') ?? 'Action'}</th>
                </tr>
              </thead>
              <tbody>
                {pendingSignals.map((sig) => (
                  <tr key={sig.signal_id} className="border-b border-border/20 last:border-0">
                    <td className="py-2 pr-3 text-xs text-secondary-text whitespace-nowrap">{formatTime(sig.created_at)}</td>
                    <td className="py-2 pr-3 font-medium text-foreground">{sig.symbol}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={sig.action === 'BUY' ? 'success' : sig.action === 'SELL' ? 'danger' : 'default'} size="sm">
                        {sig.action}
                      </Badge>
                    </td>
                    <td className="py-2 pr-3 text-secondary-text">{sig.quantity ?? '--'}</td>
                    <td className="py-2 pr-3 text-secondary-text">{(sig.confidence * 100).toFixed(0)}%</td>
                    <td className="py-2 pr-3 max-w-[200px] truncate text-secondary-text" title={sig.rationale}>
                      {sig.rationale || '--'}
                    </td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void handleConfirmSignal(sig.signal_id)}
                          disabled={confirmingId === sig.signal_id}
                          className="inline-flex items-center gap-1 rounded-lg border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-medium text-success transition-colors hover:bg-success/20 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {confirmingId === sig.signal_id ? (
                            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <CheckCircle className="h-3 w-3" />
                          )}
                          {text.confirm}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleRejectSignal(sig.signal_id)}
                          disabled={rejectingId === sig.signal_id}
                          className="inline-flex items-center gap-1 rounded-lg border border-danger/30 bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {rejectingId === sig.signal_id ? (
                            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <XCircle className="h-3 w-3" />
                          )}
                          {text.reject}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Active orders */}
      <Card padding="md">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-foreground">{text.orders}</h3>
        </div>
        {ordersLoading ? (
          <Loading />
        ) : orders.length === 0 ? (
          <EmptyState
            title={text.noOrders}
            className="border-none bg-transparent py-6 shadow-none"
            icon={<Activity className="h-5 w-5" />}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.orderId}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.symbolCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.actionCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.quantityCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.filled}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.price}</th>
                  <th className="pb-2 font-medium text-secondary-text">{t('trading.statusCol') ?? 'Status'}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.order_id} className="border-b border-border/20 last:border-0">
                    <td className="py-2 pr-3 font-mono text-xs text-secondary-text">{order.order_id.slice(0, 8)}...</td>
                    <td className="py-2 pr-3 font-medium text-foreground">{order.symbol}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={order.action === 'BUY' ? 'success' : order.action === 'SELL' ? 'danger' : 'default'} size="sm">
                        {order.action}
                      </Badge>
                    </td>
                    <td className="py-2 pr-3 text-secondary-text">{order.quantity}</td>
                    <td className="py-2 pr-3 text-secondary-text">{order.filled}</td>
                    <td className="py-2 pr-3 text-secondary-text">${order.price.toFixed(2)}</td>
                    <td className="py-2">{orderStatusBadge(order.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );

  // ============ Render: History Tab ============

  const renderHistory = () => (
    <div className="space-y-4 animate-fade-in">
      {/* Filter */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-medium text-secondary-text">{text.statusFilter}</span>
        <div className="flex flex-wrap gap-2">
          {['', 'pending', 'confirmed', 'rejected', 'expired'].map((statusValue) => (
            <button
              key={statusValue}
              type="button"
              onClick={() => handleHistoryFilter(statusValue)}
              className={cn(
                'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                historyStatusFilter === statusValue
                  ? 'border-cyan/30 bg-cyan/10 text-cyan'
                  : 'border-border/50 bg-card text-secondary-text hover:bg-hover hover:text-foreground',
              )}
            >
              {statusValue === '' ? text.allStatuses : statusBadge(statusValue, language).props.children}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {historyError ? (
        <ApiErrorAlert error={historyError} />
      ) : null}

      {historyLoading ? (
        <Loading label={text.loading} />
      ) : historySignals.length === 0 ? (
        <EmptyState
          title={text.noSignalHistory}
          icon={<PieChart className="h-6 w-6" />}
          className="border-dashed"
        />
      ) : (
        <Card padding="md">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border/40">
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.time}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.symbolCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.actionCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.quantityCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.confidenceCol}</th>
                  <th className="pb-2 pr-3 font-medium text-secondary-text">{text.statusCol}</th>
                  <th className="pb-2 font-medium text-secondary-text">{text.rationaleCol}</th>
                </tr>
              </thead>
              <tbody>
                {historySignals.map((sig) => (
                  <tr key={sig.signal_id} className="border-b border-border/20 last:border-0 hover:bg-card/30">
                    <td className="py-2.5 pr-3 text-xs text-secondary-text whitespace-nowrap">{formatTime(sig.created_at)}</td>
                    <td className="py-2.5 pr-3 font-medium text-foreground">{sig.symbol}</td>
                    <td className="py-2.5 pr-3">
                      <Badge variant={sig.action === 'BUY' ? 'success' : sig.action === 'SELL' ? 'danger' : 'default'} size="sm">
                        {sig.action}
                      </Badge>
                    </td>
                    <td className="py-2.5 pr-3 text-secondary-text">{sig.quantity ?? '--'}</td>
                    <td className="py-2.5 pr-3 text-secondary-text">{(sig.confidence * 100).toFixed(0)}%</td>
                    <td className="py-2.5 pr-3">{statusBadge(sig.status, language)}</td>
                    <td className="py-2.5 max-w-[250px] truncate text-secondary-text" title={sig.rationale}>
                      {sig.rationale || '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Pagination */}
      {historySignals.length > 0 && (
        <div className="space-y-2">
          <Pagination
            currentPage={historyPage}
            totalPages={totalHistoryPages}
            onPageChange={handleHistoryPageChange}
          />
          <p className="text-center text-xs text-muted-text">
            {text.total.replace('{total}', String(historyTotal))}
          </p>
        </div>
      )}
    </div>
  );

  // ============ Render: Main ============

  return (
    <div className="min-h-full flex flex-col rounded-[1.5rem] bg-transparent">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-white/5 px-3 py-3 sm:px-4">
        <div className="flex max-w-5xl flex-col">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">{text.title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary-text md:text-base">{text.description}</p>
        </div>
      </header>

      {/* Tab navigation */}
      <div className="flex-shrink-0 border-b border-white/5 px-3 sm:px-4">
        <nav className="flex gap-1" role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              type="button"
              aria-selected={activeTab === tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors',
                activeTab === tab.key
                  ? 'border-cyan text-foreground'
                  : 'border-transparent text-secondary-text hover:text-foreground',
              )}
            >
              {tab.icon}
              {text[tab.labelKey] as string}
            </button>
          ))}
        </nav>
      </div>

      {/* Main content */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden p-3 sm:p-4">
        <div className="mx-auto w-full max-w-5xl">
          {activeTab === 'overview' && renderOverview()}
          {activeTab === 'trade' && renderTrade()}
          {activeTab === 'history' && renderHistory()}
        </div>
      </main>
    </div>
  );
};

export default TradingPage;
