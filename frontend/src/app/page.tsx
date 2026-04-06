"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import ErrorBoundary from "@/components/ui/error-boundary";
import { screenerApi, portfolioApi, sectorsApi } from "@/lib/api";
import type { Holding } from "@/types";
import { Activity, TrendingUp, Calendar, Play } from "lucide-react";

// Local format functions
const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

const formatDate = (dateStr: string | null): string => {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getPercentColor = (value: number | null): string => {
  if (value === null || value === undefined) return 'text-gray-500';
  return value >= 0 ? 'text-green-600' : 'text-red-600';
};

export default function Dashboard() {
  const { data: screenerData, error: screenerError, mutate: mutateScreener } = useSWR(
    '/api/screener/latest',
    screenerApi.latest
  );

  const { data: portfolioData, error: portfolioError } = useSWR(
    '/api/portfolio/performance',
    portfolioApi.performance
  );

  const { data: sectorsData, error: sectorsError } = useSWR(
    '/api/sectors/performance',
    sectorsApi.performance
  );

  const handleRunScreener = async () => {
    try {
      await screenerApi.run();
      // Refresh data after run
      setTimeout(() => {
        mutateScreener();
      }, 3000);
    } catch (error) {
      console.error('Failed to run screener:', error);
    }
  };

  const isLoading = !screenerData && !screenerError && !portfolioData && !portfolioError;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <LoadingSkeleton lines={2} />
          <LoadingSkeleton lines={2} />
          <LoadingSkeleton lines={2} />
          <LoadingSkeleton lines={2} />
        </div>
        <LoadingSkeleton lines={5} />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-3xl font-bold">Dashboard Overview</h1>
          <Button onClick={handleRunScreener} className="flex items-center space-x-2">
            <Play className="h-4 w-4" />
            <span>Run Screener</span>
          </Button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Positions</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {screenerData?.total_positions || portfolioData?.total_positions || 0}
              </div>
              <p className="text-xs text-muted-foreground">
                Across 11 sectors
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg 26W Return</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${getPercentColor(portfolioData?.performance_metrics?.avg_26w_return ?? null)}`}>
                {formatPercent(portfolioData?.performance_metrics?.avg_26w_return ?? null)}
              </div>
              <p className="text-xs text-muted-foreground">
                Portfolio performance
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Strongest Sector</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {sectorsData?.summary?.strongest_sector || 'N/A'}
              </div>
              <p className="text-xs text-muted-foreground">
                By momentum score
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Next Run</CardTitle>
              <Calendar className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {screenerData?.scheduler_status?.jobs?.[0]?.next_run_time 
                  ? new Date(screenerData.scheduler_status.jobs[0].next_run_time).toLocaleTimeString('en-US', {
                      hour: '2-digit',
                      minute: '2-digit'
                    })
                  : 'N/A'
                }
              </div>
              <p className="text-xs text-muted-foreground">
                Daily snapshot
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Top Holdings */}
        <Card>
          <CardHeader>
            <CardTitle>Top 5 Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            {portfolioData?.holdings ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead>Sector</TableHead>
                    <TableHead>Weight</TableHead>
                    <TableHead className="text-right">26W Return</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {portfolioData.holdings
                    .sort((a: Holding, b: Holding) => (b.momentum_score || 0) - (a.momentum_score || 0))
                    .slice(0, 5)
                    .map((holding: Holding) => (
                      <TableRow key={holding.ticker}>
                        <TableCell className="font-medium">{holding.ticker}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{holding.sector}</Badge>
                        </TableCell>
                        <TableCell>{holding.position_weight.toFixed(2)}%</TableCell>
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
            ) : (
              <LoadingSkeleton lines={5} />
            )}
          </CardContent>
        </Card>

        {/* Sector Weights */}
        <Card>
          <CardHeader>
            <CardTitle>Sector Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            {portfolioData?.sector_weights ? (
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {(Object.entries(portfolioData.sector_weights) as [string, number][]).map(([sector, weight]) => (
                  <div key={sector} className="text-center">
                    <div className="text-lg font-semibold">{weight.toFixed(1)}%</div>
                    <div className="text-sm text-gray-600">{sector}</div>
                  </div>
                ))}
              </div>
            ) : (
              <LoadingSkeleton lines={3} />
            )}
          </CardContent>
        </Card>
      </div>
    </ErrorBoundary>
  );
}
