from __future__ import annotations

from pathlib import Path

import pytest

from bot.model_infer import ModelInferer


def _model_path() -> Path:
    return Path(__file__).resolve().parent.parent / "models" / "model.pkl"


def test_model_infer_predicts_probabilities() -> None:
    inferer = ModelInferer(model_path=_model_path())
    features = {"atr": 500.0, "adx": 40.0, "ret": 0.01, "vol": 0.002}
    proba = inferer.predict_proba(features)
    assert pytest.approx(sum(proba.values()), rel=1e-6) == 1.0
    assert 0.0 <= proba["buy"] <= 1.0
    assert 0.0 <= proba["sell"] <= 1.0


def test_model_infer_missing_feature_raises() -> None:
    inferer = ModelInferer(model_path=_model_path())
    with pytest.raises(ValueError):
        inferer.predict_proba({"atr": 1.0})
