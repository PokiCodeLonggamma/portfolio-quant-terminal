from __future__ import annotations

import numpy as np

from src.portfolio.risk import historical_var, parametric_var, risk_metrics


def test_risk_metrics_basic_shape(daily_returns):
    m = risk_metrics(daily_returns)
    assert m.sample_size == len(daily_returns)
    assert m.ann_vol > 0
    assert m.sharpe == m.ann_return / m.ann_vol
    assert m.max_drawdown <= 0
    assert m.var_95_daily <= 0
    assert m.cvar_95_daily <= m.var_95_daily


def test_parametric_var_negative_loss(daily_returns):
    var = parametric_var(daily_returns, alpha=0.95)
    assert var < 0


def test_historical_var_matches_quantile(daily_returns):
    var = historical_var(daily_returns, alpha=0.95)
    assert np.isclose(var, np.quantile(daily_returns, 0.05))
