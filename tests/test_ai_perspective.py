from app.opportunity.engine import compute_opportunity_signal
from app.services.ai_perspective_service import (
    DISCLAIMER,
    build_template_perspective,
)
from tests.test_opportunity import _bars, _uptrend_closes

_REQUIRED_KEYS = {
    "symbol",
    "market",
    "opportunity_type",
    "opportunity_score",
    "confidence",
    "source",
    "model",
    "cached",
    "summary",
    "signal_alignment",
    "key_drivers",
    "risk_factors",
    "watch_next",
    "disclaimer",
}


def _signal():
    return compute_opportunity_signal("7203.T", "Toyota", "jp", _bars(_uptrend_closes()))


def test_template_perspective_shape():
    p = build_template_perspective(_signal())
    assert _REQUIRED_KEYS.issubset(p.keys())
    assert p["source"] == "template"
    assert p["model"] is None
    assert p["cached"] is False
    assert p["summary"]
    assert p["disclaimer"] == DISCLAIMER
    assert p["signal_alignment"] in {"aligned", "mixed", "conflicting"}
    assert isinstance(p["key_drivers"], list)
    assert isinstance(p["risk_factors"], list) and p["risk_factors"]


def test_template_perspective_does_not_change_score():
    sig = _signal()
    p = build_template_perspective(sig)
    assert p["opportunity_score"] == sig.opportunity_score
    assert p["opportunity_type"] == sig.opportunity_type
