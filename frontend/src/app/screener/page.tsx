"use client";

import { useState } from "react";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import ErrorBoundary from "@/components/ui/error-boundary";
import { screenerApi } from "@/lib/api";
import type { ScreenerRun } from "@/types";
import { Play, RefreshCw } from "lucide-react";

const formatPercent = (value: number | null, decimals = 2): string => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

const getPercentColor = (value: number | null): string => {
  if (value === null || value === undefined) return 'text-gray-500';
  return value >= 0 ? 'text-green-600' : 'text-red-600';
};

export default function ScreenerPage() {
  const [activeTab, setActiveTab] = useState<string>("Information Technology");
  
  const { data: screenerData, error, mutate } = useSWR(
    '/api/screener/latest',
    screenerApi.latest,
    { refreshInterval: 30000 } // Refresh every 30 seconds
  );

  const handleRunScreener = async () => {
    try {
      await screenerApi.run();
      setTimeout(() => mutate(), 3000);
    } catch (error) {
      console.error('Failed to run screener:', error);
    }
  };

  if (error) {
    return (
      <ErrorBoundary>
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <p className="text-red-600 mb-4">Failed to load screener data</p>
          <Button onClick={() => mutate()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </div>
      </ErrorBoundary>
    );
  }

  if (!screenerData) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-3xl font-bold">Screener Results</h1>
          <Button disabled>
            <Play className="h-4 w-4 mr-2" />
            Loading...
          </Button>
        </div>
        <LoadingSkeleton lines={10} />
      </div>
    );
  }

  const sectors = Object.keys(screenerData.sectors);
  const currentSectorData = screenerData.sectors[activeTab] || [];

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">Screener Results</h1>
            <p className="text-gray-600 mt-1">
              Last run: {screenerData.run_date ? new Date(screenerData.run_date).toLocaleString() : 'Never'}
            </p>
          </div>
          <Button onClick={handleRunScreener} className="flex items-center space-x-2">
            <Play className="h-4 w-4" />
            <span>Run Screener</span>
          </Button>
        </div>

        {/* Sector Tabs */}
        <Card>
          <CardHeader>
            <CardTitle>Sectors ({screenerData.total_positions} total positions)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 mb-6">
              {sectors.map(sector => (
                <Button
                  key={sector}
                  variant={activeTab === sector ? "default" : "outline"}
                  onClick={() => setActiveTab(sector)}
                  className="flex items-center space-x-2"
                >
                  <span>{sector}</span>
                  <Badge variant="secondary" className="ml-1">
                    {screenerData.sectors[sector]?.length || 0}
                  </Badge>
                </Button>
              ))}
            </div>

            {/* Sector Table */}
            {currentSectorData.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead className="text-right">4W Return</TableHead>
                    <TableHead className="text-right">13W Return</TableHead>
                    <TableHead className="text-right">26W Return</TableHead>
                    <TableHead className="text-right">L1 Surprise</TableHead>
                    <TableHead className="text-right">L2 Surprise</TableHead>
                    <TableHead className="text-right">Weight</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {currentSectorData.map((pick: ScreenerRun) => (
                    <TableRow key={pick.ticker}>
                      <TableCell className="font-medium">{pick.ticker}</TableCell>
                      <TableCell className={`text-right ${getPercentColor(pick.returns["4W"])}`}>
                        {formatPercent(pick.returns["4W"])}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(pick.returns["13W"])}`}>
                        {formatPercent(pick.returns["13W"])}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(pick.returns["26W"])}`}>
                        {formatPercent(pick.returns["26W"])}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(pick.l1_surprise)}`}>
                        {formatPercent(pick.l1_surprise)}
                      </TableCell>
                      <TableCell className={`text-right ${getPercentColor(pick.l2_surprise)}`}>
                        {formatPercent(pick.l2_surprise)}
                      </TableCell>
                      <TableCell className="text-right">{pick.position_weight.toFixed(2)}%</TableCell>
                      <TableCell className="text-right">
                        {pick.composite_score?.toFixed(1) || 'N/A'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-center py-8 text-gray-500">
                No data available for {activeTab}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </ErrorBoundary>
  );
}
