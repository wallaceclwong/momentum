// API Response Types
export interface ScreenerRun {
  ticker: string;
  returns: {
    "4W": number | null;
    "13W": number | null;
    "26W": number | null;
  };
  composite_score: number | null;
  l1_surprise: number | null;
  l2_surprise: number | null;
  sector_etf: string;
  position_weight: number;
  run_date: string | null;
}

export interface ScreenerLatestResponse {
  run_date: string | null;
  total_positions: number;
  sectors: Record<string, ScreenerRun[]>;
  scheduler_status: SchedulerStatus;
}

export interface ScreenerHistoryItem {
  run_date: string | null;
  total_positions: number;
  sectors: Record<string, Array<{
    ticker: string;
    composite_score: number | null;
    position_weight: number;
  }>>;
}

export interface SchedulerStatus {
  running: boolean;
  jobs: Array<{
    id: string;
    name: string;
    next_run_time: string | null;
    trigger: string;
  }>;
}

export interface PerformanceLog {
  date: string | null;
  portfolio_ytd: number | null;
  spmo_ytd: number | null;
  qqq_ytd: number | null;
  total_positions: number | null;
  avg_momentum_score: number | null;
}

export interface PortfolioPerformanceResponse {
  snapshot_date: string | null;
  total_positions: number;
  sector_breakdown: Record<string, number>;
  sector_weights: Record<string, number>;
  performance_metrics: {
    avg_4w_return: number | null;
    avg_13w_return: number | null;
    avg_26w_return: number | null;
  };
  holdings: Holding[];
  performance_history: PerformanceLog[];
  scheduler_status: SchedulerStatus;
}

export interface Holding {
  ticker: string;
  sector: string;
  sector_etf: string;
  sector_weight: number;
  position_weight: number;
  returns_4w: number | null;
  returns_13w: number | null;
  returns_26w: number | null;
  composite_score: number | null;
  l1_surprise: number | null;
  l2_surprise: number | null;
  position_value: number;
  sector_weight_percent: number;
  momentum_score: number | null;
}

export interface SectorAllocationResponse {
  snapshot_date: string | null;
  sector_weights: Record<string, number>;
  sector_counts: Record<string, number>;
  sector_performance: Record<string, {
    positions: Holding[];
    total_weight: number;
    avg_4w_return: number;
    avg_13w_return: number;
    avg_26w_return: number;
    position_count: number;
  }>;
  total_weight: number;
}

export interface SectorPerformanceResponse {
  data: Record<string, {
    sector: string;
    position_count: number;
    avg_4w_return: number;
    avg_13w_return: number;
    avg_26w_return: number;
    avg_composite_score: number;
    avg_earnings_surprise: number;
    top_performers: Array<{
      ticker: string;
      composite_score: number | null;
      returns_4w: number | null;
      returns_13w: number | null;
      returns_26w: number | null;
    }>;
    rank: number;
  }>;
  rankings: Array<{
    sector: string;
    position_count: number;
    avg_4w_return: number;
    avg_13w_return: number;
    avg_26w_return: number;
    avg_composite_score: number;
    avg_earnings_surprise: number;
    top_performers: Array<{
      ticker: string;
      composite_score: number | null;
      returns_4w: number | null;
      returns_13w: number | null;
      returns_26w: number | null;
    }>;
    rank: number;
  }>;
  summary: {
    total_sectors: number;
    strongest_sector: string | null;
    weakest_sector: string | null;
  };
}

export interface SectorCorrelationResponse {
  calculation_date: string | null;
  window_days: number;
  correlation_matrix: Record<string, Record<string, number>>;
  cached: boolean;
}

export interface EtfWeightsResponse {
  weights: Record<string, {
    weight_percent: number;
    etf_ticker: string | null;
  }>;
  total_weight_percent: number;
  calculation_date: string | null;
}
