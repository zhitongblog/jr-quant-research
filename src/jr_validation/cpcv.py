"""
Combinatorial Purged Cross-Validation (CPCV).

Reference: M. López de Prado, "Advances in Financial Machine Learning", ch. 12.

Why this exists: standard k-fold CV on time-series financial data leaks future
information into the training set because feature/label windows overlap across
the train/test boundary. CPCV addresses this by:

1. Splitting the timeline into N contiguous groups.
2. For each choice of k test groups (C(N,k) combinations), training on the
   remaining N-k groups *and purging* training samples whose label horizon
   touches a test group, with an additional `embargo` of trailing days.
3. Aggregating per-combination OOS predictions into a robust performance
   distribution that is far harder to overfit than a single train/valid/test
   split.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterator

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CPCVSplit:
    """A single CPCV fold: a list of (train_idx, test_idx, test_group_ids)."""

    train_idx: np.ndarray
    test_idx: np.ndarray
    test_groups: tuple[int, ...]


def make_groups(times: pd.DatetimeIndex, n_groups: int) -> np.ndarray:
    """Assign each observation a contiguous group id in [0, n_groups)."""
    if len(times) < n_groups:
        raise ValueError(f"Cannot make {n_groups} groups from {len(times)} samples")
    int_times = pd.Series(times.astype("int64"))
    return pd.cut(int_times, bins=n_groups, labels=False).astype(int).to_numpy()


def cpcv_split(
    times: pd.DatetimeIndex,
    label_end_times: pd.DatetimeIndex,
    n_groups: int = 6,
    n_test_groups: int = 2,
    embargo_pct: float = 0.01,
) -> Iterator[CPCVSplit]:
    """
    Yield CPCV folds with purging + embargo.

    Parameters
    ----------
    times
        Datetime index of every observation (length N).
    label_end_times
        For each observation, the datetime when its label is fully realised.
        For a 1-day-forward-return label this is `times + 1 business day`.
        For monthly-return labels this is `times + ~21 business days`.
    n_groups
        Total number of contiguous time groups. Typical: 5..10.
    n_test_groups
        How many groups to hold out as test each fold. Typical: 2.
    embargo_pct
        Fraction of total samples to additionally drop after each test group's
        end (avoids label-feature leakage past purge horizon).
    """
    if len(times) != len(label_end_times):
        raise ValueError("times and label_end_times must align")

    groups = make_groups(times, n_groups)
    n = len(times)
    embargo = int(np.ceil(n * embargo_pct))

    for test_combo in combinations(range(n_groups), n_test_groups):
        test_mask = np.isin(groups, test_combo)
        test_idx = np.where(test_mask)[0]
        if len(test_idx) == 0:
            continue

        # purge: drop training samples whose label window overlaps any test sample's time range
        train_mask = ~test_mask
        for g in test_combo:
            g_idx = np.where(groups == g)[0]
            t_start, t_end = times[g_idx[0]], times[g_idx[-1]]
            # purge any train sample whose label end falls inside [t_start, t_end]
            overlap = np.asarray(label_end_times >= t_start) & np.asarray(times <= t_end)
            train_mask &= ~overlap
            # embargo: drop `embargo` train samples immediately after t_end
            after_end_positions = np.where(times > t_end)[0]
            if len(after_end_positions) > 0:
                embargo_idx = after_end_positions[:embargo]
                train_mask[embargo_idx] = False

        train_idx = np.where(train_mask)[0]
        yield CPCVSplit(train_idx=train_idx, test_idx=test_idx, test_groups=test_combo)
