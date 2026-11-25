"""A decoder variant for Python experiments on the same saved detector samples."""

from chipsldpc.prototype import minsum_decode


def decode(row_ones, priors, syndrome, max_iterations):
    """Change normalized min-sum's check-message scale from 0.75 to 0.5.

    Priors are floating-point LLRs. The result is a proposed error vector over
    DEM columns. This function never receives the measured logical observables.
    A new update rule needs a separate Scala implementation to run as RTL.
    """
    return minsum_decode(row_ones, priors, syndrome, max_iterations, scale=0.5)
