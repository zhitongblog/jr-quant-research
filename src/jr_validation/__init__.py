"""
Validation utilities for time-series financial ML, focused on overfit detection.

- `cpcv`: Combinatorial Purged K-Fold Cross-Validation (López de Prado, 2018, ch. 12).
- `pbo`:  Probability of Backtest Overfitting via CSCV (Bailey et al., 2014).

Wire these in around any factor/model search so that "best-in-IS" candidates
are not silently shipping with no OOS guarantee.
"""

from jr_validation.cpcv import CPCVSplit, cpcv_split, make_groups
from jr_validation.pbo import cscv_pbo

__all__ = ["CPCVSplit", "cpcv_split", "make_groups", "cscv_pbo"]
