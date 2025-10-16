"""Model inference helpers for the trading bot."""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

LOGGER = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    feature_names: list[str]
    version: str
    weights: dict[str, float]
    bias: float

    def predict(self, features: Mapping[str, float]) -> float:
        score = self.bias
        for name in self.feature_names:
            score += self.weights.get(name, 0.0) * float(features.get(name, 0.0))
        return 1 / (1 + math.exp(-score))


class ModelInferer:
    """Wraps a pickled model and performs inference with schema validation."""

    def __init__(self, model_path: Path | str = Path("models/model.pkl")) -> None:
        self.model_path = Path(model_path)
        self._model = self._load_model()

    def _load_model(self) -> LoadedModel:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        with self.model_path.open("rb") as fh:
            obj = pickle.load(fh)
        if not isinstance(obj, LoadedModel):
            raise TypeError("Unexpected model format")
        LOGGER.info("Loaded model version=%s features=%s", obj.version, obj.feature_names)
        return obj

    @property
    def model(self) -> LoadedModel:
        return self._model

    def predict_proba(self, feature_row: Mapping[str, float]) -> dict[str, float]:
        missing = [name for name in self.model.feature_names if name not in feature_row]
        if missing:
            message = f"Missing features: {missing}"
            LOGGER.error(message)
            raise ValueError(message)
        prob_up = self.model.predict(feature_row)
        prob_down = 1 - prob_up
        return {"buy": prob_up, "sell": prob_down}


__all__ = ["LoadedModel", "ModelInferer"]
