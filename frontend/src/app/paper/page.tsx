"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, RefreshCw, Activity, DollarSign, BarChart2, Clock } from "lucide-react";

const API = "http://localhost:8000";

function fmt(n: number | null | undefined, decimals = 2) {
  if (n == null) return "N/A";
  return n.toFixed(decimals);
}
function fmtUSD(n: number | null | undefined) {
  if (n == null) return "N/A";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(n: number | null | undefined) {
  if (n == null) return "N/A";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

interface Position {
  ticker: string;
  sector: string;
  shares: number;
  entry_price: number;
  current_price: number;
  cost_basis: number;
  market_value: number;
  gain_loss: number;
  gain_loss_pct: number;
  target_weight: number;
  entry_date: string;
}

interface Summary {
  total_positions: number;
  total_cost: number;
  total_value: number;
  total_gain_loss: number;
  total_gain_pct: number;
  trading_mode: string;
  inception_date: string;
}

interface PortfolioData {
  positions: Position[];
  summary: Summary | null;
  benchmarks: Record<string, number | null>;
}

interface Trade {
  date: string;
  action: string;
  ticker: string;
  sector: string;
  shares: number;
  price: number;
  total_value: number;
  rebalance_id: string;
  mode: string;
}

export default function PaperPortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [rebalancing, setRebalancing] = useState(false);
  const [activeTab, setActiveTab] = useState<"positions" | "trades">("positions");

  const fetchData = async () => {
    try {
      const [portRes, tradesRes] = await Promise.all([
        fetch(`${API}/api/paper/portfolio`),
        fetch(`${API}/api/paper/trades?limit=50`),
      ]);
      if (portRes.ok) setPortfolio(await portRes.json());
      if (tradesRes.ok) {
        const t = await tradesRes.json();
        setTrades(t.trades || []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const triggerRebalance = async () => {
    setRebalancing(true);
    await fetch(`${API}/api/paper/rebalance`, { method: "POST" });
    setTimeout(() => { fetchData(); setRebalancing(false); }, 35000);
  };

  const s = portfolio?.summary;
  const isPositive = (s?.total_gain_pct ?? 0) >= 0;
  const modeLabel = s?.trading_mode === "live" ? "LIVE" : "PAPER";
  const modeBadgeColor = s?.trading_mode === "live"
    ? "bg-red-500/20 text-red-400 border border-red-500/30"
    : "bg-blue-500/20 text-blue-400 border border-blue-500/30";

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white">Portfolio Tracker</h1>
              <span className={`text-xs font-bold px-2 py-1 rounded-full ${modeBadgeColor}`}>
                {modeLabel}
              </span>
            </div>
            <p className="text-gray-400 text-sm mt-1">
              Live P&amp;L tracking — switch <code className="text-blue-400">TRADING_MODE=live</code> in .env to execute real orders
            </p>
          </div>
          <button
            onClick={triggerRebalance}
            disabled={rebalancing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-900 disabled:text-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${rebalancing ? "animate-spin" : ""}`} />
            {rebalancing ? "Rebalancing (~30s)..." : "Rebalance Now"}
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-64 text-gray-500">
            <Activity className="w-6 h-6 animate-pulse mr-2" /> Loading portfolio...
          </div>
        )}

        {!loading && !s && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
            <p className="text-gray-400">No positions yet. Click <strong>Rebalance Now</strong> to seed the portfolio.</p>
          </div>
        )}

        {!loading && s && (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                  <DollarSign className="w-3.5 h-3.5" /> PORTFOLIO VALUE
                </div>
                <div className="text-xl font-bold text-white">{fmtUSD(s.total_value)}</div>
                <div className="text-xs text-gray-500 mt-1">Cost: {fmtUSD(s.total_cost)}</div>
              </div>

              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                  {isPositive ? <TrendingUp className="w-3.5 h-3.5 text-green-400" /> : <TrendingDown className="w-3.5 h-3.5 text-red-400" />}
                  TOTAL GAIN / LOSS
                </div>
                <div className={`text-xl font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}>
                  {fmtUSD(s.total_gain_loss)}
                </div>
                <div className={`text-xs mt-1 ${isPositive ? "text-green-500" : "text-red-500"}`}>
                  {fmtPct(s.total_gain_pct)}
                </div>
              </div>

              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                  <BarChart2 className="w-3.5 h-3.5" /> VS BENCHMARKS
                </div>
                <div className="space-y-1">
                  {Object.entries(portfolio?.benchmarks || {}).map(([bm, ret]) => (
                    <div key={bm} className="flex justify-between text-xs">
                      <span className="text-gray-400">{bm}</span>
                      <span className={ret != null && ret >= 0 ? "text-green-400" : "text-red-400"}>
                        {fmtPct(ret)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                  <Clock className="w-3.5 h-3.5" /> INCEPTION
                </div>
                <div className="text-sm font-semibold text-white">
                  {s.inception_date ? new Date(s.inception_date).toLocaleDateString() : "N/A"}
                </div>
                <div className="text-xs text-gray-500 mt-1">{s.total_positions} positions</div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1 w-fit">
              {(["positions", "trades"] as const).map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors capitalize ${
                    activeTab === tab ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Positions Table */}
            {activeTab === "positions" && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-400 text-xs uppercase">
                      <th className="text-left p-3">Ticker</th>
                      <th className="text-left p-3 hidden md:table-cell">Sector</th>
                      <th className="text-right p-3">Shares</th>
                      <th className="text-right p-3">Entry</th>
                      <th className="text-right p-3">Current</th>
                      <th className="text-right p-3">Value</th>
                      <th className="text-right p-3">Gain/Loss</th>
                      <th className="text-right p-3">Wt%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio!.positions.map((p, i) => {
                      const pos = p.gain_loss >= 0;
                      return (
                        <tr key={p.ticker} className={`border-b border-gray-800/50 hover:bg-gray-800/30 ${i % 2 === 0 ? "" : "bg-gray-900/50"}`}>
                          <td className="p-3 font-bold text-white">{p.ticker}</td>
                          <td className="p-3 text-gray-400 text-xs hidden md:table-cell">{p.sector}</td>
                          <td className="p-3 text-right text-gray-300">{fmt(p.shares, 2)}</td>
                          <td className="p-3 text-right text-gray-400">${fmt(p.entry_price)}</td>
                          <td className="p-3 text-right text-white">${fmt(p.current_price)}</td>
                          <td className="p-3 text-right text-gray-200">{fmtUSD(p.market_value)}</td>
                          <td className={`p-3 text-right font-medium ${pos ? "text-green-400" : "text-red-400"}`}>
                            <div>{fmtPct(p.gain_loss_pct)}</div>
                            <div className="text-xs opacity-70">{fmtUSD(p.gain_loss)}</div>
                          </td>
                          <td className="p-3 text-right text-gray-400">{fmt(p.target_weight)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Trade History */}
            {activeTab === "trades" && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-400 text-xs uppercase">
                      <th className="text-left p-3">Date</th>
                      <th className="text-left p-3">Action</th>
                      <th className="text-left p-3">Ticker</th>
                      <th className="text-left p-3 hidden md:table-cell">Sector</th>
                      <th className="text-right p-3">Shares</th>
                      <th className="text-right p-3">Price</th>
                      <th className="text-right p-3">Value</th>
                      <th className="text-right p-3 hidden md:table-cell">Mode</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                        <td className="p-3 text-gray-400 text-xs">{new Date(t.date).toLocaleDateString()}</td>
                        <td className="p-3">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded ${t.action === "BUY" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                            {t.action}
                          </span>
                        </td>
                        <td className="p-3 font-bold text-white">{t.ticker}</td>
                        <td className="p-3 text-gray-400 text-xs hidden md:table-cell">{t.sector}</td>
                        <td className="p-3 text-right text-gray-300">{fmt(t.shares, 2)}</td>
                        <td className="p-3 text-right text-gray-300">${fmt(t.price)}</td>
                        <td className="p-3 text-right text-gray-200">{fmtUSD(t.total_value)}</td>
                        <td className="p-3 text-right hidden md:table-cell">
                          <span className={`text-xs px-2 py-0.5 rounded ${t.mode === "live" ? "bg-red-500/20 text-red-400" : "bg-blue-500/20 text-blue-400"}`}>
                            {t.mode}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
