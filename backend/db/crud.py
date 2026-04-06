"""
CRUD operations for S&P 500 Momentum Screener database.
"""
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from backend.db.models import ScreenerRun, PortfolioSnapshot, PerformanceLog, SectorCorrelation, BacktestResult


def save_screener_run(
    db: Session,
    screener_results: Dict[str, List[Dict]],
    screener_summary: Dict
):
    """Save screener run results to database."""
    # Clear existing runs for the same date (to avoid duplicates)
    today = datetime.now().date()
    db.query(ScreenerRun).filter(
        ScreenerRun.run_date >= datetime.combine(today, datetime.min.time())
    ).delete()
    
    # Save new results
    for sector, picks in screener_results.items():
        for pick in picks:
            screener_run = ScreenerRun(
                sector=sector,
                ticker=pick["ticker"],
                returns_4w=pick.get("returns", {}).get("4W"),
                returns_13w=pick.get("returns", {}).get("13W"),
                returns_26w=pick.get("returns", {}).get("26W"),
                composite_score=pick.get("composite_score"),
                l1_surprise=pick.get("l1_surprise"),
                l2_surprise=pick.get("l2_surprise"),
                sector_etf=pick.get("sector_etf"),
                position_weight=pick.get("position_weight", 0) / 100,  # Convert % to decimal
                raw_data=pick
            )
            db.add(screener_run)


def save_portfolio_snapshot(
    db: Session,
    portfolio: List[Dict],
    portfolio_summary: Dict
):
    """Save portfolio snapshot to database."""
    # Clear existing snapshots for today
    today = datetime.now().date()
    db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.snapshot_date >= datetime.combine(today, datetime.min.time())
    ).delete()
    
    # Save new snapshot
    snapshot = PortfolioSnapshot(
        total_positions=portfolio_summary.get("total_positions"),
        sector_breakdown=portfolio_summary.get("sector_breakdown"),
        sector_weights=portfolio_summary.get("sector_weights"),
        avg_4w_return=portfolio_summary.get("avg_4w_return"),
        avg_13w_return=portfolio_summary.get("avg_13w_return"),
        avg_26w_return=portfolio_summary.get("avg_26w_return"),
        holdings=portfolio
    )
    db.add(snapshot)


def save_performance_log(
    db: Session,
    portfolio_summary: Dict,
    benchmark_data: Optional[Dict] = None
):
    """Save performance log to database."""
    # Clear existing logs for today
    today = datetime.now().date()
    db.query(PerformanceLog).filter(
        PerformanceLog.log_date >= datetime.combine(today, datetime.min.time())
    ).delete()
    
    # Calculate YTD returns (simplified - in production would track daily)
    portfolio_ytd = portfolio_summary.get("avg_26w_return", 0)  # Using 26W as proxy
    
    # Save performance log
    perf_log = PerformanceLog(
        portfolio_ytd=portfolio_ytd,
        spmo_ytd=benchmark_data.get("spmo_ytd", 0) if benchmark_data else 0,
        qqq_ytd=benchmark_data.get("qqq_ytd", 0) if benchmark_data else 0,
        total_positions=portfolio_summary.get("total_positions"),
        avg_momentum_score=portfolio_summary.get("avg_momentum_score"),
        raw_data={
            "portfolio_summary": portfolio_summary,
            "benchmark_data": benchmark_data
        }
    )
    db.add(perf_log)


def save_sector_correlation(
    db: Session,
    correlation_matrix: Dict,
    window_days: int = 130
):
    """Save sector correlation matrix to database."""
    # Clear existing correlations for today
    today = datetime.now().date()
    db.query(SectorCorrelation).filter(
        SectorCorrelation.calculation_date >= datetime.combine(today, datetime.min.time())
    ).delete()
    
    # Save new correlation matrix
    correlation = SectorCorrelation(
        correlation_matrix=correlation_matrix,
        window_days=window_days
    )
    db.add(correlation)


def get_latest_screener_results(db: Session) -> List[ScreenerRun]:
    """Get the most recent screener results."""
    latest_run = db.query(ScreenerRun).order_by(ScreenerRun.run_date.desc()).first()
    if not latest_run:
        return []
    
    # Use a 2-minute window around the latest run_date to avoid SQLite
    # datetime precision / timezone equality mismatches
    from datetime import timedelta
    run_time = latest_run.run_date
    return db.query(ScreenerRun).filter(
        ScreenerRun.run_date >= run_time - timedelta(minutes=2),
        ScreenerRun.run_date <= run_time + timedelta(minutes=2),
    ).all()


def get_latest_portfolio(db: Session) -> Optional[PortfolioSnapshot]:
    """Get the most recent portfolio snapshot."""
    return db.query(PortfolioSnapshot).order_by(
        PortfolioSnapshot.snapshot_date.desc()
    ).first()


def get_performance_history(db: Session, days: int = 30) -> List[PerformanceLog]:
    """Get performance history for the last N days."""
    from datetime import timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days)
    return db.query(PerformanceLog).filter(
        PerformanceLog.log_date >= cutoff_date
    ).order_by(PerformanceLog.log_date.desc()).all()


def get_latest_correlation(db: Session) -> Optional[SectorCorrelation]:
    """Get the most recent sector correlation matrix."""
    return db.query(SectorCorrelation).order_by(
        SectorCorrelation.calculation_date.desc()
    ).first()


def get_screener_history(db: Session, limit: int = 10) -> List[List[ScreenerRun]]:
    """Get historical screener runs grouped by day."""
    from datetime import timedelta
    
    recent_dates = db.query(ScreenerRun.run_date).distinct().order_by(
        ScreenerRun.run_date.desc()
    ).limit(limit).all()
    
    history = []
    for (date,) in recent_dates:
        runs = db.query(ScreenerRun).filter(
            ScreenerRun.run_date >= date - timedelta(minutes=2),
            ScreenerRun.run_date <= date + timedelta(minutes=2),
        ).all()
        history.append(runs)
    
    return history


def create_backtest_run(
    db: Session,
    start_date: datetime,
    end_date: datetime,
    rebalance_freq: str = "monthly"
) -> BacktestResult:
    """Create a new backtest run."""
    backtest = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=rebalance_freq,
        status="pending",
        parameters={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "rebalance_freq": rebalance_freq
        }
    )
    db.add(backtest)
    db.commit()
    db.refresh(backtest)
    return backtest


def update_backtest_status(
    db: Session,
    run_id: str,
    status: str,
    error_message: Optional[str] = None
) -> Optional[BacktestResult]:
    """Update backtest run status."""
    backtest = db.query(BacktestResult).filter(BacktestResult.run_id == run_id).first()
    if backtest:
        backtest.status = status
        if error_message:
            backtest.error_message = error_message
        db.commit()
        db.refresh(backtest)
    return backtest


def save_backtest_results(
    db: Session,
    run_id: str,
    results: Dict
) -> Optional[BacktestResult]:
    """Save backtest results."""
    backtest = db.query(BacktestResult).filter(BacktestResult.run_id == run_id).first()
    if backtest:
        # Update metrics
        backtest.status = "completed"
        backtest.cagr = results.get("metrics", {}).get("cagr")
        backtest.sharpe = results.get("metrics", {}).get("sharpe")
        backtest.max_drawdown = results.get("metrics", {}).get("max_drawdown")
        backtest.calmar = results.get("metrics", {}).get("calmar")
        backtest.volatility = results.get("metrics", {}).get("volatility")
        backtest.best_day = results.get("metrics", {}).get("best_day")
        backtest.worst_day = results.get("metrics", {}).get("worst_day")
        backtest.win_rate = results.get("metrics", {}).get("win_rate")
        
        # Benchmark metrics
        backtest.spy_cagr = results.get("benchmark_metrics", {}).get("SPY", {}).get("cagr")
        backtest.spmo_cagr = results.get("benchmark_metrics", {}).get("SPMO", {}).get("cagr")
        backtest.qqq_cagr = results.get("benchmark_metrics", {}).get("QQQ", {}).get("cagr")
        
        # Results data
        backtest.nav_series = results.get("nav_series", [])
        backtest.monthly_returns = results.get("monthly_returns", {})
        backtest.final_nav = results.get("final_nav")
        backtest.total_return = results.get("total_return")
        backtest.total_trades = results.get("total_trades")
        
        db.commit()
        db.refresh(backtest)
    return backtest


def get_backtest_result(db: Session, run_id: str) -> Optional[BacktestResult]:
    """Get backtest result by run_id."""
    return db.query(BacktestResult).filter(BacktestResult.run_id == run_id).first()


def get_backtest_list(db: Session, limit: int = 20) -> List[BacktestResult]:
    """Get list of backtest runs."""
    return db.query(BacktestResult).order_by(
        BacktestResult.created_at.desc()
    ).limit(limit).all()
