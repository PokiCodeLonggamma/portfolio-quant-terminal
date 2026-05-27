"""Phase 5a — MacroService tests."""
from __future__ import annotations

from src.services.macro_service import MacroService
from src.services.schemas import MacroRegimeSnapshot


def _stub_full():
    return {
        "vix_level": 18.5,
        "vix_short": 17.2,
        "vix_long": 19.4,
        "dxy": 104.8,
        "us10y_yield": 4.2,
        "spy_close": 540.0,
        "spy_ma200": 510.0,
    }


def _stub_empty():
    return {
        "vix_level": None, "vix_short": None, "vix_long": None,
        "dxy": None, "us10y_yield": None, "spy_close": None, "spy_ma200": None,
    }


def test_snapshot_returns_pydantic_with_all_fields():
    s = MacroService(fetch_fn=_stub_full)
    out = s.get_snapshot()
    assert isinstance(out, MacroRegimeSnapshot)
    assert out.vix_level == 18.5
    assert out.dxy == 104.8
    assert out.us10y_yield == 4.2
    assert out.spy_above_200d is True  # 540 > 510


def test_snapshot_classifies_contango_when_long_gt_short():
    """short=17.2, long=19.4 → contango (calm)."""
    s = MacroService(fetch_fn=_stub_full)
    out = s.get_snapshot()
    assert out.vix_term_structure == "contango"


def test_snapshot_classifies_backwardation_when_short_gt_long():
    """short=22, long=18 → backwardation (stress)."""
    def stress():
        d = _stub_full()
        d["vix_short"] = 22.0
        d["vix_long"] = 18.0
        return d
    out = MacroService(fetch_fn=stress).get_snapshot()
    assert out.vix_term_structure == "backwardation"


def test_snapshot_handles_empty_upstream():
    s = MacroService(fetch_fn=_stub_empty)
    out = s.get_snapshot()
    assert out.vix_level is None
    assert out.vix_term_structure is None
    assert out.spy_above_200d is None


def test_snapshot_spy_below_ma200():
    def bear():
        d = _stub_full()
        d["spy_close"] = 480.0
        d["spy_ma200"] = 510.0
        return d
    out = MacroService(fetch_fn=bear).get_snapshot()
    assert out.spy_above_200d is False


def test_macro_service_no_streamlit():
    import src.services.macro_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
