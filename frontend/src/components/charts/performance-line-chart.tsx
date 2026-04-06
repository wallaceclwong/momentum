"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
// Local format function since shadcn overwrote utils.ts
const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

interface PerformanceLineChartProps {
  data: Array<{
    date: string | null;
    portfolio_ytd: number | null;
    spmo_ytd: number | null;
    qqq_ytd: number | null;
  }>;
  title?: string;
}

export default function PerformanceLineChart({ data, title = "Performance History" }: PerformanceLineChartProps) {
  const chartData = data.map(item => ({
    date: item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'N/A',
    portfolio: item.portfolio_ytd || 0,
    spmo: item.spmo_ytd || 0,
    qqq: item.qqq_ytd || 0,
  })).reverse();

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border rounded shadow-sm">
          <p className="text-sm font-medium mb-2">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {formatPercent(entry.value)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis tickFormatter={(value) => `${value}%`} />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Line
              type="monotone"
              dataKey="portfolio"
              stroke="#3b82f6"
              strokeWidth={2}
              name="Portfolio"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="spmo"
              stroke="#ef4444"
              strokeWidth={2}
              name="SPMO"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="qqq"
              stroke="#10b981"
              strokeWidth={2}
              name="QQQ"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
