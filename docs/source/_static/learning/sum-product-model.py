from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def binary_finite_reduced_row_echelon(matrix: np.ndarray) -> np.ndarray:
    rref = np.array(matrix, dtype=int, copy=True) % 2
    n_rows, n_cols = rref.shape
    pivot_row = 0

    for pivot_col in range(max(n_cols - 1, 1)):
        if pivot_row >= n_rows:
            break

        candidates = np.where(rref[pivot_row:, pivot_col] == 1)[0]
        if candidates.size == 0:
            continue

        source_row = pivot_row + int(candidates[0])
        if source_row != pivot_row:
            rref[[pivot_row, source_row]] = rref[[source_row, pivot_row]]

        for row in range(n_rows):
            if row != pivot_row and rref[row, pivot_col] == 1:
                rref[row] ^= rref[pivot_row]

        pivot_row += 1

    return rref


@dataclass(frozen=True)
class BPTraceStep:
    iteration: int
    phase: str
    messages: np.ndarray
    posterior_llr: np.ndarray
    estimated_error: np.ndarray
    syndrome_match: bool


@dataclass(frozen=True)
class OSD0Trace:
    reliability_order: np.ndarray
    selected_columns: np.ndarray
    h_reduced: np.ndarray
    syndrome_reduced: np.ndarray
    augmented_rref: np.ndarray
    reduced_error: np.ndarray
    full_error: np.ndarray


def gf2_rank(matrix: np.ndarray) -> int:
    """Rank a binary matrix using Gauss-Jordan elimination."""
    reduced = np.asarray(matrix, dtype=int).copy() % 2
    pivot_row = 0

    for pivot_col in range(reduced.shape[1]):
        candidates = np.where(reduced[pivot_row:, pivot_col] == 1)[0]
        if candidates.size == 0:
            continue

        source_row = pivot_row + int(candidates[0])
        reduced[[pivot_row, source_row]] = reduced[[source_row, pivot_row]]
        for row in range(reduced.shape[0]):
            if row != pivot_row and reduced[row, pivot_col]:
                reduced[row] ^= reduced[pivot_row]

        pivot_row += 1
        if pivot_row == reduced.shape[0]:
            break

    return pivot_row


def select_independent_columns(
    h_mat: np.ndarray,
    reliability_order: np.ndarray,
) -> np.ndarray:
    """Match systolicLDPC's least-reliable independent-column selection."""
    selected: list[int] = []
    rank = 0

    for column in reliability_order:
        candidate = selected + [int(column)]
        new_rank = gf2_rank(h_mat[:, candidate])
        if new_rank > rank:
            selected.append(int(column))
            rank = new_rank
        if rank == h_mat.shape[0]:
            break

    return np.asarray(selected, dtype=int)


def default_demo_case() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the documented 3-check, 7-variable teaching example."""
    h_mat = np.array(
        [
            [1, 1, 1, 1, 0, 0, 0],
            [0, 1, 1, 0, 1, 1, 0],
            [0, 0, 1, 1, 0, 1, 1],
        ],
        dtype=int,
    )
    planted_error = np.array([0, 0, 1, 0, 0, 0, 0], dtype=int)
    syndrome = (h_mat @ planted_error) % 2
    return h_mat, planted_error, syndrome


class BPOSDDecoder:
    """A lightweight Belief Propagation + OSD-0 decoder."""

    def __init__(self, h_mat, error_rate: float = 0.05, max_iter: int = 50):
        self.H = np.asarray(h_mat, dtype=int)
        self.m, self.n = self.H.shape
        self.max_iter = max_iter
        self.channel_llr = float(np.log((1.0 - error_rate) / error_rate))

    def decode(self, syndrome: np.ndarray) -> tuple[bool, np.ndarray, str]:
        parity_matrix = self.H
        target_syndrome = np.asarray(syndrome, dtype=int)
        c2v_messages = np.zeros((self.m, self.n))
        prior_llr = self.channel_llr
        posterior_llr = np.full(self.n, prior_llr)

        for _ in range(self.max_iter):
            var_to_check_msgs = parity_matrix * (posterior_llr[None, :] - c2v_messages)
            c2v_messages = self.update_checks(var_to_check_msgs, target_syndrome)
            posterior_llr = prior_llr + (c2v_messages * parity_matrix).sum(axis=0)
            estimated_error = (posterior_llr < 0).astype(int)
            if np.all((parity_matrix @ estimated_error) % 2 == target_syndrome):
                return True, estimated_error, "BP"

        estimated_error = self.osd0(target_syndrome, posterior_llr)
        is_success = bool(np.all((parity_matrix @ estimated_error) % 2 == target_syndrome))
        return is_success, estimated_error, "OSD-0"

    def trace_rounds(
        self,
        syndrome: np.ndarray,
        *,
        rounds: int = 3,
        stop_on_success: bool = False,
    ) -> list[BPTraceStep]:
        parity_matrix = self.H
        target_syndrome = np.asarray(syndrome, dtype=int)
        c2v_messages = np.zeros((self.m, self.n))
        prior_llr = self.channel_llr
        posterior_llr = np.full(self.n, prior_llr)
        estimated_error = np.zeros(self.n, dtype=int)
        steps: list[BPTraceStep] = []

        for iteration in range(1, min(rounds, self.max_iter) + 1):
            var_to_check_msgs = parity_matrix * (posterior_llr[None, :] - c2v_messages)
            steps.append(
                BPTraceStep(
                    iteration=iteration,
                    phase="variable_to_check",
                    messages=var_to_check_msgs.copy(),
                    posterior_llr=posterior_llr.copy(),
                    estimated_error=estimated_error.copy(),
                    syndrome_match=bool(np.all((parity_matrix @ estimated_error) % 2 == target_syndrome)),
                )
            )

            c2v_messages = self.update_checks(var_to_check_msgs, target_syndrome)
            posterior_llr = prior_llr + (c2v_messages * parity_matrix).sum(axis=0)
            estimated_error = (posterior_llr < 0).astype(int)
            syndrome_match = bool(np.all((parity_matrix @ estimated_error) % 2 == target_syndrome))
            steps.append(
                BPTraceStep(
                    iteration=iteration,
                    phase="check_to_variable",
                    messages=c2v_messages.copy(),
                    posterior_llr=posterior_llr.copy(),
                    estimated_error=estimated_error.copy(),
                    syndrome_match=syndrome_match,
                )
            )

            if stop_on_success and syndrome_match:
                break

        return steps

    def update_checks(self, var_messages: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        parity_matrix = self.H
        delta = 1e-15

        tanh_msgs = np.tanh(var_messages / 2.0)
        tanh_msgs = np.where((parity_matrix == 1) & (tanh_msgs == 0.0), delta, tanh_msgs)

        masked_tanh_msgs = np.where(parity_matrix == 1, tanh_msgs, 1.0)
        check_node_prods = np.prod(masked_tanh_msgs, axis=1, keepdims=True)
        extrinsic_tanh = np.clip(check_node_prods / masked_tanh_msgs, -1 + delta, 1 - delta)

        syndrome_sign = (1 - 2 * np.asarray(syndrome, dtype=int))[:, None]
        return parity_matrix * syndrome_sign * 2.0 * np.arctanh(extrinsic_tanh)

    def osd0(self, syndrome: np.ndarray, llr: np.ndarray) -> np.ndarray:
        """Solve the least-reliable independent basis and scatter it."""
        return self.trace_osd0(syndrome, llr).full_error

    def trace_osd0(self, syndrome: np.ndarray, llr: np.ndarray) -> OSD0Trace:
        target_syndrome = np.asarray(syndrome, dtype=int)
        reliability_order = np.argsort(np.abs(llr), kind="stable")
        selected_columns = select_independent_columns(self.H, reliability_order)
        h_selected = self.H[:, selected_columns]

        row_mask = h_selected.any(axis=1)
        h_reduced = h_selected[row_mask]
        syndrome_reduced = target_syndrome[row_mask]
        if h_reduced.shape[0] != h_reduced.shape[1]:
            raise ValueError("OSD-0 reduced system must be square")

        augmented = np.hstack([h_reduced, syndrome_reduced[:, None]])
        augmented_rref = binary_finite_reduced_row_echelon(augmented)
        reduced_error = augmented_rref[:, -1]

        full_error = np.zeros(self.n, dtype=int)
        full_error[selected_columns] = reduced_error
        return OSD0Trace(
            reliability_order=reliability_order,
            selected_columns=selected_columns,
            h_reduced=h_reduced,
            syndrome_reduced=syndrome_reduced,
            augmented_rref=augmented_rref,
            reduced_error=reduced_error,
            full_error=full_error,
        )
