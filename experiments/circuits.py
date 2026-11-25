"""Example circuit factory. Edit this function to study another circuit or noise model."""

import stim


def make_circuit(p: float, rounds: int = 3) -> stim.Circuit:
    """Distance-three repetition memory with circuit-level noise."""
    return stim.Circuit.generated(
        "repetition_code:memory",
        distance=3,
        rounds=rounds,
        after_clifford_depolarization=p,
        before_round_data_depolarization=p,
        after_reset_flip_probability=p,
        before_measure_flip_probability=p,
    )
