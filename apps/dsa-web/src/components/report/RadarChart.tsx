import type React from 'react';
import {
  Radar,
  RadarChart as ReChartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from 'recharts';
import type { RadarDataItem } from '../../types/analysis';

interface RadarChartProps {
  data: RadarDataItem[];
  size?: number | string;
}

/**
 * 股票评分雷达图组件
 */
export const RadarChart: React.FC<RadarChartProps> = ({ data, size = 300 }) => {
  if (!data || data.length === 0) {
    return null;
  }

  return (
    <div style={{ width: '100%', height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <ReChartsRadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fill: 'var(--muted-text)', fontSize: 12 }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={false}
            axisLine={false}
          />
          <Radar
            name="Score"
            dataKey="value"
            stroke="var(--home-accent)"
            fill="var(--home-accent)"
            fillOpacity={0.6}
          />
        </ReChartsRadarChart>
      </ResponsiveContainer>
    </div>
  );
};
