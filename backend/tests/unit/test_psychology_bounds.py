"""Psychology combined multiplier must stay inside hard bounds whatever the factors say."""
import pytest

from app.services.scoring import psychology_engine as pe


def _factor(m):
    return pe.PsychologyFactor(name="x", multiplier=m, real_signal={"appearances_found": 1, "days_since_last": 1,
                                                                    "competitor_events_same_weekend": 1, "posts_in_window": 9},
                               explanation="")


@pytest.mark.parametrize("ms,expected", [((0.1, 0.1, 0.1), pe.COMBINED_MIN), ((9, 9, 9), pe.COMBINED_MAX), ((1, 1, 1), 1.0)])
async def test_combined_multiplier_clamped(monkeypatch, ms, expected):
    async def a(*_): return _factor(ms[0])
    async def b(*_): return _factor(ms[1])
    async def c(*_): return _factor(ms[2])
    monkeypatch.setattr(pe, "_exposure_factor", a)
    monkeypatch.setattr(pe, "_fomo_factor", b)
    monkeypatch.setattr(pe, "_controversy_factor", c)
    rep = await pe.compute_psychology_report(None, "e")
    assert rep.combined_multiplier == expected


def test_factor_caps_are_sane():
    assert 0 < pe.MAX_SATURATION_PENALTY < 1 and pe.MAX_NOVELTY_BONUS < 1
    assert pe.COMBINED_MIN < 1 < pe.COMBINED_MAX
