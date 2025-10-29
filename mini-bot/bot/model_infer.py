"""Model inference helpers for the trading bot."""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

LOGGER = logging.getLogger(__name__)


def _sigmoid(value: float) -> float:
    if value > 50:
        return 1.0
    if value < -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


@dataclass
class LoadedModel:
    """Simple logistic baseline kept for tests/offline experimentation."""

    feature_names: list[str]
    version: str
    weights: dict[str, float]
    bias: float

    def margin(self, features: Mapping[str, float]) -> float:
        score = self.bias
        for name in self.feature_names:
            score += self.weights.get(name, 0.0) * float(features.get(name, 0.0))
        return score

    def predict_proba_raw(self, features: Mapping[str, float]) -> float:
        return _sigmoid(self.margin(features))


class ModelInferer:
    """Wrap a pickled model (LightGBM or LoadedModel) and perform inference."""

    def __init__(self, model_path: Path | str = Path("models/model.pkl")) -> None:
        self.model_path = Path(model_path)
        self._model: Any = None
        self._feature_names: list[str] = []
        self._is_lightgbm = False
        self._platt_params: Optional[tuple[float, float]] = None
        self._isotonic = None
        self._load_model()
        self._load_calibration()

    # ---------------------------------------------------------------------
    # Loading helpers
    # ---------------------------------------------------------------------
    def _load_pickle(self, path: Path) -> Any:
        with path.open("rb") as fh:
            return pickle.load(fh)

    def _load_model(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")

        obj = self._load_pickle(self.model_path)

        if isinstance(obj, LoadedModel):
            self._model = obj
            self._feature_names = list(obj.feature_names)
            LOGGER.info(
                "Loaded logistic model version=%s features=%s",
                obj.version,
                len(obj.feature_names),
            )
            return

        try:  # pragma: no cover - exercised when lightgbm available
            import lightgbm as lgb  # type: ignore

            booster = None
            if isinstance(obj, lgb.Booster):
                booster = obj
            elif isinstance(obj, dict) and obj.get("type") == "lightgbm":
                booster = obj.get("model")
            if booster is not None and hasattr(booster, "feature_name"):
                self._model = booster
                self._feature_names = list(booster.feature_name())
                self._is_lightgbm = True
                LOGGER.info(
                    "Loaded LightGBM booster with %s features",
                    len(self._feature_names),
                )
                return
        except Exception as exc:  # pragma: no cover - optional dependency
            raise TypeError(f"Unexpected model format: {type(obj)!r}") from exc

        raise TypeError(f"Unsupported model format: {type(obj)!r}")

    def _load_calibration(self) -> None:
        calib_path = self.model_path.with_name("isotonic.pkl")
        if not calib_path.exists():
            return

        try:
            calib_obj = self._load_pickle(calib_path)
        except Exception as exc:  # pragma: no cover - optional asset
            LOGGER.warning("Failed to load calibration: %s", exc)
            return

        if isinstance(calib_obj, dict) and {"a", "b"} <= set(calib_obj):
            a = float(calib_obj["a"])
            b = float(calib_obj["b"])
            self._platt_params = (a, b)
            LOGGER.info("Loaded Platt calibrator")
            return

        if hasattr(calib_obj, "predict"):
            self._isotonic = calib_obj
            LOGGER.info("Loaded Isotonic calibrator")
            return

        LOGGER.warning("Unsupported calibration format: %r", type(calib_obj))

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    @property
    def feature_names(self) -> list[str]:
        return list(self._feature_names)

    def _validate_features(self, feature_row: Mapping[str, float]) -> Optional[str]:
        missing = [name for name in self._feature_names if name not in feature_row]
        if missing:
            return f"Missing features: {missing}"
        for name in self._feature_names:
            try:
                value = float(feature_row[name])
            except Exception:
                return f"Non-numeric value for feature '{name}'"
            if not math.isfinite(value):
                return f"Non-finite value for feature '{name}'"
        return None

    def _predict_raw(self, feature_row: Mapping[str, float]) -> tuple[float, float]:
        if self._is_lightgbm:
            booster = self._model
            vector = [float(feature_row[name]) for name in self._feature_names]
            raw_margin = float(booster.predict([vector], raw_score=True)[0])
        else:
            raw_margin = float(self._model.margin(feature_row))
        raw_prob = _sigmoid(raw_margin)
        return raw_margin, raw_prob

    def _apply_calibration(self, margin: float, prob: float) -> float:
        if self._platt_params is not None:
            a, b = self._platt_params
            return _sigmoid(a * margin + b)
        if self._isotonic is not None:
            try:
                calibrated = float(self._isotonic.predict([prob])[0])
            except Exception as exc:  # pragma: no cover - optional asset
                LOGGER.warning("Isotonic calibration failed: %s", exc)
                return prob
            return max(0.0, min(1.0, calibrated))
        return prob

    def predict_proba(self, feature_row: Mapping[str, float]) -> Optional[dict[str, float]]:
        error = self._validate_features(feature_row)
        if error:
            LOGGER.error(error)
            return None

        raw_margin, raw_prob = self._predict_raw(feature_row)
        calibrated_prob = self._apply_calibration(raw_margin, raw_prob)
        calibrated_prob = max(0.0, min(1.0, calibrated_prob))
        return {
            "buy": calibrated_prob,
            "sell": 1.0 - calibrated_prob,
            "debug_raw_prob": raw_prob,
            "debug_raw_margin": raw_margin,
        }


__all__ = ["LoadedModel", "ModelInferer"]
