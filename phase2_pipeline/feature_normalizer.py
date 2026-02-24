"""Online feature normalization using Welford's algorithm."""

from __future__ import annotations

import math
from typing import Optional


class FeatureNormalizer:
    """Track rolling mean/variance per feature and produce z-scores.

    Uses Welford's online algorithm for numerically stable incremental
    mean and variance computation.
    """

    def __init__(self, clip: float = 3.0):
        self.clip = clip
        self._count: dict[str, int] = {}
        self._mean: dict[str, float] = {}
        self._m2: dict[str, float] = {}

    def update(self, raw_features: dict) -> None:
        """Incorporate a new observation into the running statistics."""
        for key, value in raw_features.items():
            if value is None:
                continue
            try:
                val = float(value)
            except (TypeError, ValueError):
                continue

            if key not in self._count:
                self._count[key] = 0
                self._mean[key] = 0.0
                self._m2[key] = 0.0

            self._count[key] += 1
            n = self._count[key]
            delta = val - self._mean[key]
            self._mean[key] += delta / n
            delta2 = val - self._mean[key]
            self._m2[key] += delta * delta2

    def normalize(self, raw_features: dict) -> dict:
        """Return z-score normalized features, clipped to [-clip, +clip]."""
        result: dict[str, Optional[float]] = {}
        for key, value in raw_features.items():
            if value is None:
                result[key] = None
                continue
            try:
                val = float(value)
            except (TypeError, ValueError):
                result[key] = None
                continue

            n = self._count.get(key, 0)
            if n < 2:
                result[key] = 0.0
                continue

            variance = self._m2[key] / (n - 1)
            std = math.sqrt(variance) if variance > 0 else 0.0

            if std == 0.0:
                result[key] = 0.0
            else:
                z = (val - self._mean[key]) / std
                z = max(-self.clip, min(self.clip, z))
                result[key] = z

        return result

    @property
    def sample_count(self) -> int:
        """Return the minimum sample count across all tracked features."""
        if not self._count:
            return 0
        return min(self._count.values())
