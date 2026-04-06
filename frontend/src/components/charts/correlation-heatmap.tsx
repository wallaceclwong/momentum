"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface CorrelationHeatmapProps {
  data: Record<string, Record<string, number>>;
  title?: string;
}

export default function CorrelationHeatmap({ data, title = "Sector Correlation Matrix" }: CorrelationHeatmapProps) {
  const sectors = Object.keys(data);
  
  const getColor = (value: number): string => {
    if (value >= 0.7) return 'bg-green-500';
    if (value >= 0.3) return 'bg-green-300';
    if (value >= -0.3) return 'bg-gray-300';
    if (value >= -0.7) return 'bg-red-300';
    return 'bg-red-500';
  };

  const getTextColor = (value: number): string => {
    return Math.abs(value) >= 0.5 ? 'text-white' : 'text-gray-800';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <div className="min-w-full inline-block">
            <div className="grid grid-cols-12 gap-1 text-xs">
              {/* Header row */}
              <div className="col-span-1"></div>
              {sectors.map(sector => (
                <div key={sector} className="font-semibold text-center p-1">
                  {sector}
                </div>
              ))}
              
              {/* Data rows */}
              {sectors.map(rowSector => (
                <React.Fragment key={rowSector}>
                  <div className="font-semibold text-right pr-2 p-1">
                    {rowSector}
                  </div>
                  {sectors.map(colSector => {
                    const value = data[rowSector]?.[colSector] || 0;
                    return (
                      <div
                        key={`${rowSector}-${colSector}`}
                        className={`w-full h-8 flex items-center justify-center rounded ${getColor(value)} ${getTextColor(value)}`}
                        title={`${rowSector} vs ${colSector}: ${value.toFixed(3)}`}
                      >
                        {value.toFixed(2)}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
        
        <div className="mt-4 flex items-center justify-center space-x-4 text-xs">
          <div className="flex items-center space-x-1">
            <div className="w-4 h-4 bg-red-500 rounded"></div>
            <span>-1.0 to -0.7</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-4 h-4 bg-red-300 rounded"></div>
            <span>-0.7 to -0.3</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-4 h-4 bg-gray-300 rounded"></div>
            <span>-0.3 to 0.3</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-4 h-4 bg-green-300 rounded"></div>
            <span>0.3 to 0.7</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-4 h-4 bg-green-500 rounded"></div>
            <span>0.7 to 1.0</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
