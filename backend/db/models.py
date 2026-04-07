"""
SQLAlchemy models for S&P 500 Momentum Screener database.
"""
import uuid
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class ScreenerRun(Base):
    """Model for storing screener run results."""
    __tablename__ = "screener_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    run_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sector = Column(String(100), nullable=False, index=True)
    ticker = Column(String(10), nullable=False, index=True)
    
    # Momentum metrics
    returns_4w = Column(Float)
    returns_13w = Column(Float)
    returns_26w = Column(Float)
    composite_score = Column(Float)
    
    # Earnings data
    l1_surprise = Column(Float)
    l2_surprise = Column(Float)
    
    # Position info
    sector_etf = Column(String(10))
    position_weight = Column(Float)  # as percentage
    
    # Raw data for debugging
    raw_data = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioSnapshot(Base):
    """Model for storing portfolio snapshots."""
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Portfolio summary
    total_positions = Column(Integer)
    sector_breakdown = Column(JSON)  # dict of sector -> count
    sector_weights = Column(JSON)    # dict of sector -> weight%
    
    # Performance metrics
    avg_4w_return = Column(Float)
    avg_13w_return = Column(Float)
    avg_26w_return = Column(Float)
    
    # Holdings data (JSON array of position details)
    holdings = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PerformanceLog(Base):
    """Model for storing daily performance logs."""
    __tablename__ = "performance_log"
    
    id = Column(Integer, primary_key=True, index=True)
    log_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Portfolio metrics
    portfolio_ytd = Column(Float)  # Year-to-date return
    spmo_ytd = Column(Float)        # SPMO ETF YTD return
    qqq_ytd = Column(Float)         # Nasdaq 100 YTD return
    
    # Additional metrics
    total_positions = Column(Integer)
    avg_momentum_score = Column(Float)
    
    # Raw data for analysis
    raw_data = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SectorCorrelation(Base):
    """Model for storing sector correlation data."""
    __tablename__ = "sector_correlation"
    
    id = Column(Integer, primary_key=True, index=True)
    calculation_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Correlation matrix (JSON)
    correlation_matrix = Column(JSON)
    
    # Metadata
    window_days = Column(Integer, default=130)  # 26 weeks
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaperPosition(Base):
    """Current open positions in the paper (or live) portfolio."""
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), nullable=False, unique=True, index=True)
    sector = Column(String(100))
    shares = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_date = Column(DateTime(timezone=True), nullable=False)
    target_weight = Column(Float)
    trading_mode = Column(String(10), default="paper")  # paper | live
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PaperTrade(Base):
    """Historical trade log for paper (or live) portfolio."""
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(DateTime(timezone=True), nullable=False, index=True)
    action = Column(String(4), nullable=False)   # BUY | SELL
    ticker = Column(String(10), nullable=False, index=True)
    sector = Column(String(100))
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    rebalance_id = Column(String(36))            # groups all trades from one rebalance
    trading_mode = Column(String(10), default="paper")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BacktestResult(Base):
    """Model for storing backtest results."""
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    
    # Backtest parameters
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    rebalance_freq = Column(String(20), default="monthly")
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    
    # Performance metrics
    cagr = Column(Float)
    sharpe = Column(Float)
    max_drawdown = Column(Float)
    calmar = Column(Float)
    volatility = Column(Float)
    best_day = Column(Float)
    worst_day = Column(Float)
    win_rate = Column(Float)
    
    # Benchmark comparison
    spy_cagr = Column(Float)
    spmo_cagr = Column(Float)
    qqq_cagr = Column(Float)
    
    # Results data
    nav_series = Column(JSON)  # List of {date, nav}
    monthly_returns = Column(JSON)  # Monthly returns matrix
    parameters = Column(JSON)  # Input parameters
    
    # Summary stats
    final_nav = Column(Float)
    total_return = Column(Float)
    total_trades = Column(Integer)
    
    # Error information
    error_message = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
