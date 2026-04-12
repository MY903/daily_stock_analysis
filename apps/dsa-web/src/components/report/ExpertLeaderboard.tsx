import type React from 'react';
import { useEffect, useState } from 'react';
import { agentApi, type ExpertPerformanceItem } from '../../api/agent';
import { Card, Loading } from '../common';
import { Trophy, TrendingUp } from 'lucide-react';

/**
 * 专家胜率榜单组件
 */
export const ExpertLeaderboard: React.FC = () => {
  const [performance, setPerformance] = useState<ExpertPerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPerformance = async () => {
      try {
        const response = await agentApi.getExpertPerformance();
        setPerformance(response.performance);
      } catch (error) {
        console.error('Failed to fetch expert performance:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPerformance();
  }, []);

  if (loading) {
    return (
      <Card variant="bordered" padding="md" className="flex items-center justify-center min-h-[200px]">
        <Loading label="加载榜单中..." />
      </Card>
    );
  }

  if (performance.length === 0) {
    return null;
  }

  return (
    <Card variant="bordered" padding="md" className="home-panel-card flex flex-col h-full overflow-hidden">
      <div className="flex items-baseline gap-2 mb-4">
        <span className="label-uppercase">Expert Rankings</span>
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
          <Trophy className="w-4 h-4 text-warning" />
          大师胜率榜单
        </h3>
      </div>
      
      <div className="space-y-3 overflow-y-auto pr-1">
        {performance.map((item, index) => (
          <div key={item.id} className="flex items-center gap-3 p-2.5 rounded-lg bg-background/40 border border-border/40">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
              index === 0 ? 'bg-warning text-warning-foreground' : 
              index === 1 ? 'bg-slate-300 text-slate-800' :
              index === 2 ? 'bg-amber-600 text-white' : 'bg-muted text-muted-foreground'
            }`}>
              {index + 1}
            </div>
            
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold truncate text-foreground">{item.name}</span>
                <span className="text-xs font-mono text-success flex items-center gap-0.5">
                  <TrendingUp className="w-3 h-3" />
                  {item.win_rate}%
                </span>
              </div>
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-[10px] text-muted-text">已结算: {item.settled_count} 场</span>
                <span className="text-[10px] text-muted-text">胜场: {item.win_count}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
