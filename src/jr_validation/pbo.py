"""
Probability of Backtest Overfitting (PBO) via Combinatorially-Symmetric
Cross-Validation (CSCV).

Reference:
  Bailey, Borwein, López de Prado, Zhu (2014), "The Probability of Backtest
  Overfitting", Journal of Computational Finance.

The intuition: given the IS (in-sample) performance of N strategies on each
of S CSCV folds, count how often the IS-best strategy is also OOS-best.
If IS performance is a noisy signal of OOS performance, you will see the
IS-best strategy rank OOS at random — PBO measures how much worse than
50/50 it does.
"""
from __future__ import annotations

from itertools import combinations
from typing import Sequence

import numpy as np


def cscv_pbo(
    returns_matrix: np.ndarray,
    n_splits: int = 16,
    metric: str = "sharpe",
) -> dict[str, float]:
    """
    Probability of Backtest Overfitting via CSCV.

    Parameters
    ----------
    returns_matrix
        Shape (T, N) — per-period returns for N candidate strategies.
    n_splits
        Number of equal-sized time blocks. Must be even. CSCV picks all
        C(n_splits, n_splits/2) ways to partition into IS/OOS halves.
    metric
        "sharpe" (default) or "mean".

    Returns
    -------
    {"pbo": float, "n_combinations": int, "logits": np.ndarray}
        pbo is in [0, 1]; values >> 0.5 indicate severe overfitting risk.
    """
    if n_splits % 2 != 0:
        raise ValueError("n_splits must be even")
    T, N = returns_matrix.shape
    if T < n_splits * 2:
        raise ValueError(f"Need at least {n_splits * 2} rows for {n_splits} splits, got {T}")

    # Split rows into n_splits blocks of (approximately) equal size
    block_starts = np.linspace(0, T, n_splits + 1).astype(int)
    blocks = [returns_matrix[block_starts[i] : block_starts[i + 1]] for i in range(n_splits)]

    def _metric(arr: np.ndarray) -> np.ndarray:
        if metric == "sharpe":
            mean = arr.mean(axis=0)
            std = arr.std(axis=0, ddof=1)
            std = np.where(std < 1e-12, np.nan, std)
            return mean / std
        if metric == "mean":
            return arr.mean(axis=0)
        raise ValueError(f"Unknown metric: {metric}")

    logits = []
    half = n_splits // 2
    for is_blocks in combinations(range(n_splits), half):
        oos_blocks = tuple(set(range(n_splits)) - set(is_blocks))
        is_data = np.concatenate([blocks[i] for i in is_blocks], axis=0)
        oos_data = np.concatenate([blocks[i] for i in oos_blocks], axis=0)

        is_perf = _metric(is_data)
        oos_perf = _metric(oos_data)

        if np.all(np.isnan(is_perf)) or np.all(np.isnan(oos_perf)):
            continue

        best_is = int(np.nanargmax(is_perf))
        # OOS rank of the IS-best strategy, in [1, N]
        # Use scipy-free implementation: rank = #{x : x <= best_is_oos} (handle ties via avg)
        oos_best_score = oos_perf[best_is]
        valid = ~np.isnan(oos_perf)
        if np.isnan(oos_best_score):
            continue
        rank = (1 + (oos_perf[valid] < oos_best_score).sum() + 0.5 * (oos_perf[valid] == oos_best_score).sum())
        n_valid = int(valid.sum())
        # normalized to (0, 1)
        relative_rank = rank / (n_valid + 1)
        # logit transform; clamp away from 0/1
        relative_rank = np.clip(relative_rank, 1e-3, 1 - 1e-3)
        logits.append(np.log(relative_rank / (1 - relative_rank)))

    logits_arr = np.array(logits)
    pbo = float((logits_arr < 0).mean()) if len(logits_arr) else float("nan")
    return {
        "pbo": pbo,
        "n_combinations": len(logits_arr),
        "logits": logits_arr,
    }


def _self_test() -> None:
    """Tiny sanity check: random strategies should give PBO ≈ 0.5."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.01, size=(2000, 50))  # 2000 days, 50 strategies, all noise
    out = cscv_pbo(returns, n_splits=10)
    print(f"All-noise PBO: {out['pbo']:.3f}  (expected ~0.5)  n_combos={out['n_combinations']}")

    # Inject one "real" strategy with small alpha — PBO should drop
    returns[:, 0] += 0.0005
    out = cscv_pbo(returns, n_splits=10)
    print(f"One-good-strategy PBO: {out['pbo']:.3f}  (expected < 0.5)")


if __name__ == "__main__":
    _self_test()
