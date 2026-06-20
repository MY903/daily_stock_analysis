import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { Card, Loading } from '../common';
import type { DecisionSignalItem } from '../../types/decisionSignals';

interface TrendSummary {
  total: number;
  buy: number;
  sell: number;
  hold: number;
  alert: number;
  avgConfidence: number;
  healthScore: number; // 0-100 based on signal balance and recency
}

interface SignalTrendPanelProps {
  /** Optional stock code to filter trend data */
  stockCode?: string;
  /** Class name override */
  className?: string;
}

/**
 * SignalTrendPanel - shows a summary dashboard of decision signal activity.
 * Displays action distribution, average confidence, and a health score.
 */
export default function SignalTrendPanel({ stockCode, className }: SignalTrendPanelProps) {
  const [loading, setLoading] = useState(true);
  const [signals, setSignals] = useState<DecisionSignalItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await decisionSignalsApi.list({
        ...(stockCode ? { stockCode } : {}),
        pageSize: 50,
        page: 1,
      });
      setSignals(result.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load signal trends');
    } finally {
      setLoading(false);
    }
  }, [stockCode]);

  useEffect(() => {
    fetchSignals();
  }, [fetchSignals]);

  const summary: TrendSummary = useMemo(() => {
    const totals = { total: 0, buy: 0, sell: 0, hold: 0, alert: 0, confidenceSum: 0 };
    for (const s of signals) {
      totals.total++;
      const action = (s.action ?? '').toLowerCase();
      if (['buy', 'strong_buy', 'add'].includes(action)) totals.buy++;
      else if (['sell', 'strong_sell', 'reduce'].includes(action)) totals.sell++;
      else if (['hold', 'watch'].includes(action)) totals.hold++;
      else if (['alert', 'avoid'].includes(action)) totals.alert++;
      if (s.confidence != null) totals.confidenceSum += s.confidence;
    }
    const avgConf = totals.total > 0 ? totals.confidenceSum / totals.total : 0;
    // Health score: 0-100, based on buy/sell balance and confidence
    const totalActionable = totals.buy + totals.sell;
    const balanceRatio = totalActionable > 0 ? Math.min(totals.buy, totals.sell) / totalActionable : 1;
    const confidenceFactor = avgConf;
    const healthScore = Math.round(((1 - balanceRatio) * 0.4 + confidenceFactor * 0.6) * 100);
    return { ...totals, avgConfidence: avgConf, healthScore };
  }, [signals]);

  if (loading) {
    return (
      <Card className={className}>
        <div className="p-4">
          <Loading />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <div className="p-4 text-red-500 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Signal Trend Dashboard
          </h3>
          <span className="text-xs text-gray-500">{summary.total} signals</span>
        </div>

        {/* Health score */}
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>Signal Health</span>
            <span>{summary.healthScore}/100</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                summary.healthScore >= 70 ? 'bg-green-500' :
                summary.healthScore >= 40 ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${summary.healthScore}%` }}
            />
          </div>
        </div>

        {/* Action distribution */}
        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="bg-green-50 rounded p-2">
            <TrendingUp className="w-4 h-4 mx-auto mb-1 text-green-600" />
            <div className="text-lg font-semibold text-green-700">{summary.buy}</div>
            <div className="text-xs text-green-600">Buy</div>
          </div>
          <div className="bg-red-50 rounded p-2">
            <TrendingDown className="w-4 h-4 mx-auto mb-1 text-red-600" />
            <div className="text-lg font-semibold text-red-700">{summary.sell}</div>
            <div className="text-xs text-red-600">Sell</div>
          </div>
          <div className="bg-gray-50 rounded p-2">
            <Minus className="w-4 h-4 mx-auto mb-1 text-gray-600" />
            <div className="text-lg font-semibold text-gray-700">{summary.hold}</div>
            <div className="text-xs text-gray-600">Hold</div>
          </div>
          <div className="bg-yellow-50 rounded p-2">
            <AlertTriangle className="w-4 h-4 mx-auto mb-1 text-yellow-600" />
            <div className="text-lg font-semibold text-yellow-700">{summary.alert}</div>
            <div className="text-xs text-yellow-600">Alert</div>
          </div>
        </div>

        {/* Average confidence */}
        <div className="mt-3 text-xs text-gray-500 text-center">
          Avg Confidence: {(summary.avgConfidence * 100).toFixed(0)}%
        </div>
      </div>
    </Card>
  );
}
