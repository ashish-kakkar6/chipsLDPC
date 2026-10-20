#!/usr/bin/env python3
"""Check or render the frozen BB144 documentation figures without simulation.

--check uses only the Python standard library. Rendering (default, or --render) needs
Matplotlib and writes SVG/PNG figures plus a rendering receipt in the bundle.
It never reads build/generated or the sibling presentation repository.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


DEFAULT_BUNDLE = Path(__file__).resolve().parents[1] / "source/_static/bb144-results/legacy-v1"
CSV_HASHES = {
    "vanilla": "b09eeed3adc30aa241e96680df7502c90078e5f01fa9e08207f4fd5114813260",
    "relay": "3cf54a4fecd1e14c335c7d6cd18fb6aa89dcfe3685cd23c7e5302d08a6a12ca9",
    "budget": "4c19cbaa7da9343103f9d0902fb41e8abef128cfc0556c78f398eeedc03cabba",
}
COLORS = {"vanilla": "#2458a6", "relay": "#087e8b", "budget": "#ad4d20"}
FIGURES = ("vanilla-rate", "relay-rate", "relay-budget")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected, label):
    require(math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-14),
            f"{label}: {actual} != {expected}")


def wilson(failures, shots):
    z = 1.959963984540054
    center = (failures / shots + z * z / (2 * shots)) / (1 + z * z / shots)
    radius = z * math.sqrt(failures * (shots - failures) / shots**3
                           + z * z / (4 * shots**2)) / (1 + z * z / shots)
    return max(0.0, center - radius), min(1.0, center + radius)


def per_cycle(probability):
    return 1.0 if probability == 1 else -math.expm1(math.log1p(-probability) / 12)


def check_inputs(bundle):
    manifest = json.loads((bundle / "manifest.json").read_text())
    require(manifest["schema"] == "chipsldpc.docs.bb144-legacy-bundle.v1", "unexpected bundle schema")
    require(manifest["records"] == {"vanilla": 7, "relay": 7, "budget": 8}, "unexpected record counts")
    for name, record in manifest["files"].items():
        path = bundle / name
        require(path.is_file(), f"missing bundled input: {name}")
        require(path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
                f"bundled input changed: {name}")
    proof = json.loads((bundle / "presentation-provenance.json").read_text())
    metadata = json.loads((bundle / "metadata.json").read_text())
    rows = {}
    for name, expected_hash in CSV_HASHES.items():
        path = bundle / f"{name}.csv"
        require(sha256(path) == expected_hash == proof["sources"][name]["sha256"],
                f"{name}: CSV differs from the archived presentation data")
        with path.open(newline="") as stream:
            rows[name] = [{key: float(value) for key, value in row.items()}
                          for row in csv.DictReader(stream)]
        require(len(rows[name]) == manifest["records"][name], f"{name}: wrong row count")
        profile = metadata["profiles"][name]
        require(profile["schema"] == "chipsldpc.bb144.v2", f"{name}: wrong historical schema")
        require(profile["sampling"]["seed"] == 14412, f"{name}: unexpected seed")
        expected_shots = 20000 if name == "budget" else 1000
        require(profile["sampling"]["shots_per_p"] == expected_shots, f"{name}: wrong shots metadata")
        require((profile["dem"]["m"], profile["dem"]["n"], profile["dem"]["e"])
                == (936, 8784, 30672), f"{name}: wrong reduced graph")
        require((profile["dem"]["raw_m"], profile["dem"]["raw_n"],
                 profile["dem"]["logical_observables"], profile["dem"]["singleton_eliminations"])
                == (1008, 8856, 12, 72), f"{name}: wrong model dimensions")
        config = json.loads((bundle / f"{name}-config.json").read_text())
        require((config["message_bits"], config["soft_bits"], config["m"], config["n"])
                == (4, 7 if name == "vanilla" else 5, 936, 8784), f"{name}: wrong arithmetic profile")
        if name == "vanilla":
            require(config["iterations"] == 30, "vanilla: wrong iteration cap")
        else:
            initial, relay_r = (80, 600) if name == "relay" else (60, 67)
            require((config["initial_iterations"], config["relay_iterations"],
                     config["paper_R_relay_legs_after_initial"], config["solution_target"],
                     config["seed_offset"], config["maximum_legs_total"], config["maximum_total_iterations"])
                    == (initial, 60, relay_r, 5, 0, relay_r + 1, initial + 60 * relay_r),
                    f"{name}: wrong Relay profile")
        for index, row in enumerate(rows[name]):
            label = f"{name}[{index}]"
            shots, failures = row["shots"], row["failures"]
            require(shots == expected_shots and failures.is_integer() and 0 <= failures <= shots,
                    f"{label}: invalid counts")
            close(row["word_failure_probability"], failures / shots, label + " word probability")
            low, high = wilson(failures, shots)
            close(row["word_failure_ci95_low"], low, label + " Wilson lower bound")
            close(row["word_failure_ci95_high"], high, label + " Wilson upper bound")
            if name != "budget":
                close(row["logical_failure_rate_per_qec_cycle"], per_cycle(failures / shots), label + " rate")
                close(row["logical_rate_ci95_low"], per_cycle(low), label + " rate lower bound")
                close(row["logical_rate_ci95_high"], per_cycle(high), label + " rate upper bound")
                require(row["bp_nonconverged"] + row["bp_converged_logical_failures"] == failures,
                        label + ": failure components disagree")
            else:
                require(row["max_bp_iterations"] == 60 * (row["paper_R"] + 1), label + ": wrong budget")
                require(0 < row["mean_executed_iterations"] <= row["max_bp_iterations"], label + ": invalid mean")
                require(row["mean_iterations_ci95_half_width"] >= 0, label + ": invalid mean interval")
        expected_p = [.003] if name == "budget" else [i / 1000 for i in range(1, 8)]
        require(profile["sampling"]["p_values"] == expected_p, f"{name}: wrong physical probability points")
        if name != "budget":
            require([row["p"] for row in rows[name]] == expected_p, f"{name}: wrong CSV probability points")
    expected_r = [0, 1, 2, 4, 8, 16, 33, 67]
    require([row["paper_R"] for row in rows["budget"]] == metadata["budget"]["R"] == expected_r,
            "wrong budget R values")
    require([row["max_bp_iterations"] for row in rows["budget"]] == metadata["budget"]["max_bp_iterations"],
            "budget metadata differs from CSV")
    require([row["p"] for row in rows["relay"] if row["failures"] == 0] == [.001, .002],
            "unexpected zero-failure points")
    return rows


def check_figures(bundle):
    receipt = json.loads((bundle / "figures.json").read_text())
    require(receipt["manifest_sha256"] == sha256(bundle / "manifest.json"), "figures use a different manifest")
    require(receipt["renderer_sha256"] == sha256(Path(__file__)), "renderer changed; regenerate figures")
    expected = {f"{name}.{suffix}" for name in FIGURES for suffix in ("svg", "png")}
    require(set(receipt["figures"]) == expected, "incomplete figure set")
    for name, digest in receipt["figures"].items():
        require(sha256(bundle / name) == digest, f"figure changed: {name}")


def render(bundle, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullFormatter, ScalarFormatter

    plt.rcParams.update({"font.size": 11, "axes.titlesize": 15, "axes.labelsize": 11,
                         "font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "svg.hashsalt": "chipsldpc-bb144-legacy-v1", "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "white"})

    def save(figure, name):
        figure.savefig(bundle / f"{name}.svg", metadata={"Date": None})
        figure.savefig(bundle / f"{name}.png", dpi=180)
        plt.close(figure)

    for name, title, subtitle in (
            ("vanilla", "Vanilla BP", "30-iteration cap · 1,000 shots per point"),
            ("relay", "Relay-5", r"$T_0=80$, $T_r=60$, $R=600$ · 1,000 shots per point")):
        figure, axis = plt.subplots(figsize=(8, 4.8), layout="constrained")
        positive = [row for row in rows[name] if row["failures"] > 0]
        x = [100 * row["p"] for row in positive]
        y = [row["logical_failure_rate_per_qec_cycle"] for row in positive]
        axis.errorbar(x, y, yerr=([row["logical_failure_rate_per_qec_cycle"] - row["logical_rate_ci95_low"]
                                   for row in positive],
                                  [row["logical_rate_ci95_high"] - row["logical_failure_rate_per_qec_cycle"]
                                   for row in positive]),
                      fmt="o-", color=COLORS[name], linewidth=1.7, markersize=5,
                      capsize=3, label="Estimate with Wilson 95% interval")
        zero = [row for row in rows[name] if row["failures"] == 0]
        if zero:
            axis.scatter([100 * row["p"] for row in zero], [row["logical_rate_ci95_high"] for row in zero],
                         marker="v", s=55, facecolors="white", edgecolors=COLORS[name], linewidths=1.5,
                         label="Zero failures: upper Wilson 95% bound", zorder=3)
        axis.set(yscale="log", xlabel="Physical error probability p (%)",
                 ylabel=r"Equivalent per-cycle failure, $q_{\mathrm{equiv}}$",
                 xticks=[i / 10 for i in range(1, 8)], xlim=(.075, .725))
        axis.set_title(title + "\n" + subtitle, loc="left", pad=12)
        axis.grid(True, which="both", alpha=.2)
        axis.legend(loc="best", fontsize=9, frameon=True, framealpha=.95)
        save(figure, name + "-rate")

    data = rows["budget"]
    figure, axis = plt.subplots(figsize=(8, 4.9), layout="constrained")
    x = [row["mean_executed_iterations"] for row in data]
    y = [row["word_failure_probability"] for row in data]
    axis.errorbar(x, y, xerr=[row["mean_iterations_ci95_half_width"] for row in data],
                  yerr=([row["word_failure_probability"] - row["word_failure_ci95_low"] for row in data],
                        [row["word_failure_ci95_high"] - row["word_failure_probability"] for row in data]),
                  fmt="o-", color=COLORS["budget"], linewidth=1.7, markersize=5, capsize=3)
    for index, row in enumerate(data):
        axis.annotate(f"R={int(row['paper_R'])}", (x[index], y[index]),
                      xytext=(7, 9 if index < 4 else 5), textcoords="offset points", fontsize=9)
    axis.set(xscale="log", yscale="log", xlabel="Mean executed BP iterations per shot",
             ylabel=r"Word-failure probability, $P_{\mathrm{word}}$", xlim=(11, 142), ylim=(.00042, .055))
    axis.set_xticks([15, 20, 30, 50, 75, 100])
    axis.xaxis.set_major_formatter(ScalarFormatter())
    axis.xaxis.set_minor_formatter(NullFormatter())
    axis.set_title("Relay-5: iteration-budget sweep\n"
                   r"$p=0.3\%$, $T_0=T_r=60$, $B=60(R+1)$ · 20,000 shots per point", loc="left", pad=12)
    axis.grid(True, which="both", alpha=.2)
    save(figure, "relay-budget")
    receipt = {"schema": "chipsldpc.docs.bb144-figures.v1",
               "manifest_sha256": sha256(bundle / "manifest.json"),
               "renderer_sha256": sha256(Path(__file__)), "matplotlib": matplotlib.__version__,
               "figures": {f"{name}.{suffix}": sha256(bundle / f"{name}.{suffix}")
                           for name in FIGURES for suffix in ("svg", "png")}}
    (bundle / "figures.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify frozen inputs, formulas and existing figures; stdlib only")
    action.add_argument("--render", action="store_true", help="validate inputs and regenerate the six SVG/PNG files")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    rows = check_inputs(args.bundle)
    if not args.check:
        render(args.bundle, rows)
    check_figures(args.bundle)
    print("PASS: 22 archived records, profile settings, Wilson intervals, rate transforms, budgets and figure hashes.")
    print("The saved horizontal mean intervals are hash-checked; raw iteration samples are not bundled.")


if __name__ == "__main__":
    main()
