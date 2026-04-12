import type React from 'react';
import type { EnsembleReports } from '../../types/analysis';
import { Card, Badge } from '../common';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface MasterVotingDiskProps {
  reports?: EnsembleReports;
}

const ANALYST_NAMES: Record<string, string> = {
  warren_buffett: '巴菲特',
  li_lu: '李录',
  paul_tudor_jones: '保罗·都铎·琼斯',
  jensen_huang: '黄仁勋',
  nassim_taleb: '塔勒布',
  ray_dalio: '雷·达里奥'
};

/**
 * 大师投票盘组件
 */
export const MasterVotingDisk: React.FC<MasterVotingDiskProps> = ({ reports }) => {
  if (!reports || Object.keys(reports).length === 0) {
    return (
      <Card variant="bordered" padding="md" className="flex items-center justify-center h-full">
        <p className="text-muted-text text-sm italic">暂无专家委员会投票数据</p>
      </Card>
    );
  }

  const getSignalIcon = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'bullish':
      case 'strong buy':
      case 'buy':
        return <TrendingUp className="w-4 h-4 text-success" />;
      case 'bearish':
      case 'strong sell':
      case 'sell':
        return <TrendingDown className="w-4 h-4 text-danger" />;
      default:
        return <Minus className="w-4 h-4 text-muted-text" />;
    }
  };

  const getSignalLabel = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'bullish':
      case 'strong buy':
      case 'buy':
        return '看多';
      case 'bearish':
      case 'strong sell':
      case 'sell':
        return '看空';
      default:
        return '中性';
    }
  };

  const getSignalVariant = (signal: string): 'success' | 'danger' | 'warning' | 'info' => {
    switch (signal.toLowerCase()) {
      case 'bullish':
      case 'strong buy':
      case 'buy':
        return 'success';
      case 'bearish':
      case 'strong sell':
      case 'sell':
        return 'danger';
      default:
        return 'info';
    }
  };

  return (
    <Card variant="bordered" padding="md" className="home-panel-card flex flex-col h-full overflow-hidden">
      <div className="flex items-baseline gap-2 mb-4">
        <span className="label-uppercase">Expert Consensus</span>
        <h3 className="text-sm font-semibold text-foreground">大师投票盘</h3>
      </div>
      
      <div className="grid grid-cols-1 gap-3 overflow-y-auto pr-1">
        {Object.entries(reports).map(([id, report]) => (
          <div key={id} className="flex items-center justify-between p-2 rounded-lg bg-background/40 border border-border/40">
            <div className="flex flex-col">
              <span className="text-xs font-medium text-foreground">{ANALYST_NAMES[id] || id}</span>
              <span className="text-[10px] text-muted-text flex items-center gap-1">
                置信度: {report.confidence}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              {getSignalIcon(report.signal)}
              <Badge variant={getSignalVariant(report.signal)} className="text-[10px] py-0 px-1.5 h-5">
                {getSignalLabel(report.signal)}
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
