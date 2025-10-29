from __future__ import annotations

from pathlib import Path

import pytest

from math import inf, nan

from bot.model_infer import ModelInferer


def _model_path() -> Path:
    return Path(__file__).resolve().parent.parent / "models" / "model.pkl"


def test_model_infer_predicts_probabilities() -> None:
    inferer = ModelInferer(model_path=_model_path())
    features = {"atr": 500.0, "adx": 40.0, "ret": 0.01, "vol": 0.002}
    proba = inferer.predict_proba(features)
    assert {"buy", "sell", "debug_raw_prob", "debug_raw_margin"} <= set(proba)
    assert pytest.approx(proba["buy"] + proba["sell"], rel=1e-9) == 1.0
    assert 0.0 <= proba["buy"] <= 1.0
    assert 0.0 <= proba["sell"] <= 1.0


def test_model_infer_missing_feature_returns_none() -> None:
    inferer = ModelInferer(model_path=_model_path())
    assert inferer.predict_proba({"atr": 1.0}) is None


@pytest.mark.parametrize(
    "bad_value",
    [nan, inf, -inf, "oops"],
)
def test_model_infer_rejects_non_finite_values(bad_value: object) -> None:
    inferer = ModelInferer(model_path=_model_path())
    features = {"atr": 1.0, "adx": 1.0, "ret": 0.0, "vol": 0.0}
    features["ret"] = bad_value  # type: ignore[index]
    assert inferer.predict_proba(features) is None
