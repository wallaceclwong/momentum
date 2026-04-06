"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import ErrorBoundary from "@/components/ui/error-boundary";
import SectorPieChart from "@/components/charts/sector-pie-chart";
import PerformanceLineChart from "@/components/charts/performance-line-chart";
import { portfolioApi } from "@/lib/api";
import type { Holding } from "@/types";

const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

const formatCurrency = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
};

const getPercentColor = (value: number | null): string => {
  if (value === null || value === undefined) return 'text-gray-500';
  return value >= 0 ? 'text-green-600' : 'text-red-600';
};

export default function PortfolioPage() {
  const { data: portfolioData, error } = useSWR(
    '/api/portfolio/performance',
    portfolioApi.performance,
    { refreshInterval: 30000 }
  );

  if (error) {
    return (
      <ErrorBoundary>
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <p className="text-red-600 mb-4">Failed to load portfolio data</p>
        </div>
      </ErrorBoundary>
    );
  }

  if (!portfolioData) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Portfolio Holdings</h1>
        <LoadingSkeleton lines={10} />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Portfolio Holdings</h1>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Total Positions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{portfolioData.total_positions}</div>
              <p className="text-sm text-gray-600">Across 11 sectors</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Avg 26W Return</CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${getPercentColor(portfolioData.performance_metrics.avg_26w_return)}`}>
                {formatPercent(portfolioData.performance_metrics.avg_26w_return)}
              </div>
              <p className="text-sm text-gray-600">Portfolio performance</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Last Updated</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold">
                {portfolioData.snapshot_date 
                  ? new Date(portfolioData.snapshot_date).toLocaleDateString()
                  : 'N/A'
                }
              </div>
              <p className="text-sm text-gray-600">Portfolio snapshot</p>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {portfolioData.sector_weights && (
            <SectorPieChart data={portfolioData.sector_weights} />
          )}
          
          {portfolioData.performance_history && (
            <PerformanceLineChart data={portfolioData.performance_history} />
          )}
        </div>

        {/* Holdings Table */}
        <Card>
          <CardHeader>
            <CardTitle>All Holdings ({portfolioData.total_positions})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Sector</TableHead>
                  <TableHead>ETF</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead className="text-right">4W Return</TableHead>
                  <TableHead className="text-right">13W Return</TableHead>
                  <TableHead className="text-right">26W Return</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portfolioData.holdings.map((holding: Holding) => (
                  <TableRow key={holding.ticker}>
                    <TableCell className="font-medium">{holding.ticker}</TableCell>
                    <TableCell>{holding.sector}</TableCell>
                    <TableCell>{holding.sector_etf}</TableCell>
                    <TableCell className="text-right">{holding.position_weight.toFixed(2)}%</TableCell>
                    <TableCell className="text-right">{formatCurrency(holding.position_value)}</TableCell>
                    <TableCell className={`text-right ${getPercentColor(holding.returns_4w)}`}>
                      {formatPercent(holding.returns_4w)}
                    </TableCell>
                    <TableCell className={`text-right ${getPercentColor(holding.returns_13w)}`}>
                      {formatPercent(holding.returns_13w)}
                    </TableCell>
                    <TableCell className={`text-right ${getPercentColor(holding.returns_26w)}`}>
                      {formatPercent(holding.returns_26w)}
                    </TableCell>
                    <TableCell className="text-right">
                      {holding.momentum_score?.toFixed(1) || 'N/A'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </ErrorBoundary>
  );
}
