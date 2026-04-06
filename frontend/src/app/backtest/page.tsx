"use client";

import { useState } from "react";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import ErrorBoundary from "@/components/ui/error-boundary";
import { backtestApi } from "@/lib/api";
import type { BacktestResult, BacktestRequest, BacktestComparison } from "@/types";
import { Play, BarChart3, TrendingUp, TrendingDown, Calendar } from "lucide-react";

const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const pct = value * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(decimals)}%`;
};

const getPercentColor = (value: number | null): string => {
  if (value === null || value === undefined) return 'text-gray-500';
  return value >= 0 ? 'text-green-600' : 'text-red-600';
};

export default function BacktestPage() {
  const [runId, setRunId] = useState<string | null>(null);
  const [formData, setFormData] = useState<BacktestRequest>({
    start_date: '2020-01-01',
    end_date: new Date().toISOString().split('T')[0],
    rebalance_freq: 'monthly'
  });

  const { data: backtestData, error, mutate } = useSWR<BacktestResult>(
    runId ? `/api/backtest/${runId}` : null,
    () => backtestApi.get(runId!),
    {
      refreshInterval: (data) => (data?.status === 'running' ? 5000 : 0),
      revalidateOnFocus: false,
    }
  );

  const { data: backtestList } = useSWR(
    '/api/backtest/list',
    () => backtestApi.list(),
    { refreshInterval: 30000 }
  );

  const handleRunBacktest = async () => {
    try {
      const response = await backtestApi.run(formData);
      setRunId(response.run_id);
      mutate(); // Trigger immediate fetch
    } catch (error) {
      console.error('Failed to run backtest:', error);
    }
  };

  const isRunning = backtestData?.status === 'running';
  const isCompleted = backtestData?.status === 'completed';

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Backtesting</h1>

        {/* Backtest Form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <BarChart3 className="h-5 w-5" />
              <span>Run Backtest</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium mb-1">Start Date</label>
                <input
                  type="date"
                  value={formData.start_date}
                  onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  className="w-full p-2 border rounded"
                  disabled={isRunning}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">End Date</label>
                <input
                  type="date"
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  className="w-full p-2 border rounded"
                  disabled={isRunning}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Rebalance Frequency</label>
                <select
                  value={formData.rebalance_freq}
                  onChange={(e) => setFormData({ ...formData, rebalance_freq: e.target.value })}
                  className="w-full p-2 border rounded"
                  disabled={isRunning}
                >
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <div className="flex items-end">
                <Button
                  onClick={handleRunBacktest}
                  disabled={isRunning}
                  className="w-full"
                >
                  {isRunning ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-2" />
                      Run Backtest
                    </>
                  )}
                </Button>
              </div>
            </div>

            {runId && (
              <div className="flex items-center space-x-2 text-sm">
                <span>Run ID:</span>
                <Badge variant="outline">{runId}</Badge>
                <Badge variant={backtestData?.status === 'completed' ? 'default' : 'secondary'}>
                  {backtestData?.status || 'pending'}
                </Badge>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results */}
        {isCompleted && backtestData && (
          <>
            {/* Performance Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">CAGR</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getPercentColor(backtestData.metrics?.cagr ?? null)}`}>
                    {formatPercent(backtestData.metrics?.cagr ?? null)}
                  </div>
                  <p className="text-xs text-gray-600">Annual return</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Sharpe Ratio</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {backtestData.metrics?.sharpe?.toFixed(2) || 'N/A'}
                  </div>
                  <p className="text-xs text-gray-600">Risk-adjusted return</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Max Drawdown</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getPercentColor(backtestData.metrics?.max_drawdown ?? null)}`}>
                    {formatPercent(backtestData.metrics?.max_drawdown ?? null)}
                  </div>
                  <p className="text-xs text-gray-600">Worst decline</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Total Return</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getPercentColor(backtestData.total_return ?? null)}`}>
                    {formatPercent(backtestData.total_return ?? null)}
                  </div>
                  <p className="text-xs text-gray-600">Overall performance</p>
                </CardContent>
              </Card>
            </div>

            {/* Benchmark Comparison */}
            <Card>
              <CardHeader>
                <CardTitle>Benchmark Comparison</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Metric</TableHead>
                      <TableHead className="text-right">Portfolio</TableHead>
                      <TableHead className="text-right">SPY (S&P 500)</TableHead>
                      <TableHead className="text-right">SPMO (Momentum)</TableHead>
                      <TableHead className="text-right">QQQ (Nasdaq)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="font-medium">CAGR</TableCell>
                      <TableCell className={`text-right ${getPercentColor(backtestData.metrics?.cagr ?? null)}`}>
                        {formatPercent(backtestData.metrics?.cagr ?? null)}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(backtestData.benchmark_metrics?.SPY?.cagr ?? null)}`}>
                        {formatPercent(backtestData.benchmark_metrics?.SPY?.cagr ?? null)}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(backtestData.benchmark_metrics?.SPMO?.cagr ?? null)}`}>
                        {formatPercent(backtestData.benchmark_metrics?.SPMO?.cagr ?? null)}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(backtestData.benchmark_metrics?.QQQ?.cagr ?? null)}`}>
                        {formatPercent(backtestData.benchmark_metrics?.QQQ?.cagr ?? null)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Summary Stats */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center space-x-2">
                    <TrendingUp className="h-4 w-4" />
                    <span>Best Day</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getPercentColor(backtestData.metrics?.best_day ?? null)}`}>
                    {formatPercent(backtestData.metrics?.best_day ?? null)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center space-x-2">
                    <TrendingDown className="h-4 w-4" />
                    <span>Worst Day</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getPercentColor(backtestData.metrics?.worst_day ?? null)}`}>
                    {formatPercent(backtestData.metrics?.worst_day ?? null)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center space-x-2">
                    <Calendar className="h-4 w-4" />
                    <span>Total Trades</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {backtestData.total_trades || 0}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* Recent Backtests */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Backtests</CardTitle>
          </CardHeader>
          <CardContent>
            {backtestList ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run ID</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Start Date</TableHead>
                    <TableHead>End Date</TableHead>
                    <TableHead className="text-right">Total Return</TableHead>
                    <TableHead className="text-right">CAGR</TableHead>
                    <TableHead className="text-right">Sharpe</TableHead>
                    <TableHead className="text-right">Max DD</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backtestList.map((test: any) => (
                    <TableRow 
                      key={test.run_id}
                      className="cursor-pointer hover:bg-gray-50"
                      onClick={() => setRunId(test.run_id)}
                    >
                      <TableCell className="font-medium">{test.run_id.slice(0, 8)}...</TableCell>
                      <TableCell>
                        <Badge variant={test.status === 'completed' ? 'default' : 'secondary'}>
                          {test.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{test.start_date}</TableCell>
                      <TableCell>{test.end_date}</TableCell>
                      <TableCell className={`text-right font-semibold ${getPercentColor(test.total_return ?? null)}`}>
                        {formatPercent(test.total_return ?? null)}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(test.cagr ?? null)}`}>
                        {formatPercent(test.cagr ?? null)}
                      </TableCell>
                      <TableCell className="text-right">
                        {test.sharpe?.toFixed(2) || 'N/A'}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(test.max_drawdown ?? null)}`}>
                        {formatPercent(test.max_drawdown ?? null)}
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
      </div>
    </ErrorBoundary>
  );
}
