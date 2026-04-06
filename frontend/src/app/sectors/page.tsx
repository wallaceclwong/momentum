"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import ErrorBoundary from "@/components/ui/error-boundary";
import CorrelationHeatmap from "@/components/charts/correlation-heatmap";
import { sectorsApi } from "@/lib/api";
import type { EtfWeight, SectorRanking } from "@/types";

const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

const getPercentColor = (value: number | null): string => {
  if (value === null || value === undefined) return 'text-gray-500';
  return value >= 0 ? 'text-green-600' : 'text-red-600';
};

export default function SectorsPage() {
  const { data: performanceData, error: perfError } = useSWR(
    '/api/sectors/performance',
    sectorsApi.performance
  );

  const { data: correlationData, error: corrError } = useSWR(
    '/api/sectors/correlation',
    sectorsApi.correlation
  );

  const { data: etfWeightsData, error: weightsError } = useSWR(
    '/api/sectors/etf-weights',
    sectorsApi.etfWeights
  );

  if (perfError || corrError || weightsError) {
    return (
      <ErrorBoundary>
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <p className="text-red-600 mb-4">Failed to load sector data</p>
        </div>
      </ErrorBoundary>
    );
  }

  if (!performanceData || !correlationData || !etfWeightsData) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Sector Analysis</h1>
        <LoadingSkeleton lines={10} />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Sector Analysis</h1>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Total Sectors</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{performanceData.summary.total_sectors}</div>
              <p className="text-sm text-gray-600">Analyzed sectors</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Strongest Sector</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{performanceData.summary.strongest_sector || 'N/A'}</div>
              <p className="text-sm text-gray-600">By momentum score</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Weakest Sector</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{performanceData.summary.weakest_sector || 'N/A'}</div>
              <p className="text-sm text-gray-600">By momentum score</p>
            </CardContent>
          </Card>
        </div>

        {/* Sector Rankings */}
        <Card>
          <CardHeader>
            <CardTitle>Sector Rankings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {performanceData.rankings.map((sector: SectorRanking, index: number) => (
                <div key={sector.sector} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <div className="flex items-center space-x-2">
                        <Badge variant={index === 0 ? "default" : "secondary"}>
                          #{sector.rank}
                        </Badge>
                        <h3 className="font-semibold">{sector.sector}</h3>
                      </div>
                      <p className="text-sm text-gray-600">{sector.position_count} positions</p>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold ${getPercentColor(sector.avg_26w_return)}`}>
                        {formatPercent(sector.avg_26w_return)}
                      </div>
                      <p className="text-xs text-gray-500">26W avg</p>
                    </div>
                  </div>
                  
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span>Avg Score:</span>
                      <span>{sector.avg_composite_score?.toFixed(1) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>4W Return:</span>
                      <span className={getPercentColor(sector.avg_4w_return)}>
                        {formatPercent(sector.avg_4w_return)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>13W Return:</span>
                      <span className={getPercentColor(sector.avg_13w_return)}>
                        {formatPercent(sector.avg_13w_return)}
                      </span>
                    </div>
                  </div>

                  {sector.top_performers.length > 0 && (
                    <div className="mt-3 pt-3 border-t">
                      <p className="text-xs text-gray-600 mb-1">Top Performers:</p>
                      <div className="flex flex-wrap gap-1">
                        {sector.top_performers.slice(0, 3).map((stock: { ticker: string }) => (
                          <Badge key={stock.ticker} variant="outline" className="text-xs">
                            {stock.ticker}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Correlation Matrix */}
        <CorrelationHeatmap 
          data={correlationData.correlation_matrix}
          title={`Correlation Matrix (${correlationData.window_days} days)`}
        />

        {/* ETF Weights */}
        <Card>
          <CardHeader>
            <CardTitle>Sector ETF Weights</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {(Object.entries(etfWeightsData.weights) as [string, EtfWeight][]).map(([sector, data]) => (
                <div key={sector} className="text-center p-3 border rounded">
                  <div className="font-semibold">{sector}</div>
                  <div className="text-lg font-bold text-blue-600">
                    {data.weight_percent.toFixed(1)}%
                  </div>
                  <div className="text-sm text-gray-500">{data.etf_ticker}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 text-center text-sm text-gray-600">
              Total Weight: {etfWeightsData.total_weight_percent.toFixed(1)}%
            </div>
          </CardContent>
        </Card>
      </div>
    </ErrorBoundary>
  );
}
