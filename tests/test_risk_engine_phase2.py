from app.risk.engine import PositionExposure, RiskEngine


def test_compute_atr_and_limits():
    engine = RiskEngine()
    atr = engine.compute_atr(
        highs=[11, 12, 13],
        lows=[9, 10, 11],
        closes=[10, 11, 12],
    )
    assert atr > 0
    assert engine.can_open_new_position(open_count=3, max_positions=5) is True
    assert engine.hit_daily_loss_limit(daily_loss_pct=2.1, daily_loss_limit_pct=2.0) is True
    assert engine.hit_stop_count_limit(stop_count=5, stop_count_limit=5) is True


def test_margin_forced_close_priority():
    engine = RiskEngine()
    exposures = [
        PositionExposure(position_id=1, strategy_id="4", market_value=100.0),
        PositionExposure(position_id=2, strategy_id="1", market_value=100.0),
        PositionExposure(position_id=3, strategy_id="2", market_value=100.0),
    ]
    # 합계 300, 기준자본 150일 때 우선순위 1,2,3,5,4 전략 순으로 정리되어야 한다.
    order = engine.margin_forced_close_order(
        exposures=exposures,
        daily_base_capital=150.0,
        priority=["1", "2", "3", "5", "4"],
    )
    assert order == [2, 3]
