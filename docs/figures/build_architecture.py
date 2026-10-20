#!/usr/bin/env python3
"""Generate the BP architecture SVGs using only the Python standard library.

Run without arguments to regenerate; --check fails if checked-in assets differ.
Coordinates and labels are kept here so every diagram remains editable.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


DESTINATION = Path(__file__).resolve().parents[1] / "source" / "_static" / "figures"
NAVY = "#16324f"
BLUE = "#235fa4"
TEAL = "#167d8d"
SLATE = "#4b6074"
LINE = "#d4dfe8"
SUBSCRIPTS = str.maketrans("ᵢⱼₖₜᵣ₀₁₂₃", "ijktr0123")


def inline_label(value: str) -> str:
    """Render real SVG subscripts instead of relying on font fallback glyphs."""
    pieces = re.split(r"([ᵢⱼₖₜᵣ₀₁₂₃][ᵢⱼₖₜᵣ₀₁₂₃,]*)", value)
    return "".join(
        '<tspan baseline-shift="-25%" font-size="75%">'
        + escape(piece.translate(SUBSCRIPTS)) + '</tspan>'
        if piece and piece[0] in "ᵢⱼₖₜᵣ₀₁₂₃" else escape(piece)
        for piece in pieces
    )


class Figure:
    def __init__(self, name: str, title: str, description: str, height: int):
        self.name = name
        self.height = height
        self.parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" '
            f'viewBox="0 0 900 {height}" role="img" '
            f'aria-labelledby="{name}-title {name}-desc">',
            f'<title id="{name}-title">{escape(title)}</title>',
            f'<desc id="{name}-desc">{escape(description)}</desc>',
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{SLATE}"/></marker></defs>',
            '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#16324f;'
            'font-size:17px} .small{font-size:15px;fill:#4b6074}'
            '.label{font-size:16px;font-weight:600;fill:#235fa4}'
            '.heading{font-size:25px;font-weight:700}'
            '.box-title{font-size:17px;font-weight:600}'
            '.wire{fill:none;stroke:#4b6074;stroke-width:1.7;'
            'stroke-linecap:round;stroke-linejoin:round}</style>',
            f'<rect width="900" height="{height}" fill="white"/>',
        ]

    def text(self, x: float, y: float, lines: str | list[str], *, anchor="start", cls="", gap=23):
        if isinstance(lines, str):
            lines = [lines]
        self.parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">')
        for index, line in enumerate(lines):
            self.parts.append(f'<tspan x="{x}" dy="{0 if index == 0 else gap}">{inline_label(line)}</tspan>')
        self.parts.append('</text>')

    def box(self, x, y, width, height, title, lines=(), *, fill="#f5f9fd", stroke=BLUE):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                          f'rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
        self.text(x + width / 2, y + 28, title, anchor="middle", cls="box-title")
        if lines:
            self.text(x + width / 2, y + 48, list(lines), anchor="middle", cls="small", gap=19)

    def wire(self, points, *, arrow=True):
        path = " L ".join(f"{x} {y}" for x, y in points)
        marker = ' marker-end="url(#arrow)"' if arrow else ''
        self.parts.append(f'<path class="wire" d="M {path}"{marker}/>')

    def dot(self, x, y):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{SLATE}"/>')

    def header(self, title, subtitle):
        self.text(30, 39, title, cls="heading")
        self.text(30, 68, subtitle, cls="small")
        self.parts.append(f'<path d="M 30 84 H 870" stroke="{LINE}"/>')

    def register(self, x, y, width, height, labels):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                          f'rx="8" fill="#eaf5f5" stroke="{TEAL}" stroke-width="1.7"/>')
        self.parts.append(f'<path d="M {x} {y+height-31} l 10 8 l -10 8" '
                          f'fill="none" stroke="{TEAL}" stroke-width="1.7"/>')
        for text, center_y in labels:
            self.text(x + width / 2, center_y + 6, text, anchor="middle", cls="label")

    def finish(self):
        result = "\n".join(self.parts + ['</svg>', ''])
        ET.fromstring(result)
        return result


def cnu():
    f = Figure("cnu", "CNU: shared parity and minima",
               "For check i, canonical signs feed one shared syndrome-adjusted XOR reduction. "
               "XOR with the recipient sign gives the exclusive sign. Magnitudes feed a duplicate-preserving "
               "two-minimum tree; both minima are scaled once. A comparison of each input magnitude with "
               "the raw first minimum generates its selector. One register stores the shared scaled pair "
               "and per-edge sign and selector, enabled by step.fire. An illustrative combinational "
               "XOR tree below shows three canonical sign inputs reduced with the stored syndrome.", 885)
    f.parts.append('<style>.syndrome{font-size:15px;font-weight:700;fill:#4b6074}</style>')
    f.header("CNU · shared parity and minima", "Check i · combinational CheckNode followed by its StaticCheckStage register")
    f.text(30, 132, "Sign path", cls="label")
    f.text(790, 127, "Result register", anchor="middle", cls="label")
    f.box(30, 170, 145, 70, "Canonical sign", ["bⱼ = [Rᵢ,ⱼ < 0]"])
    f.box(235, 170, 165, 70, "Shared XOR", ["signs ⊕ syndrome"])
    f.box(470, 170, 170, 70, "Exclude edge j", ["sᵢ,ⱼ = Pᵢ ⊕ bⱼ"])
    f.register(725, 155, 145, 345, [("sᵢ,ⱼ", 205), ("m₁, m₂", 365), ("cᵢ,ⱼ", 460)])
    f.wire([(175, 205), (235, 205)])
    f.dot(200, 205)
    f.wire([(200, 205), (200, 102), (555, 102), (555, 170)])
    f.text(435, 124, "own sign bⱼ", anchor="middle", cls="small")
    f.text(317, 145, "stored syndrome σᵢ", anchor="middle", cls="syndrome")
    f.wire([(317, 150), (317, 170)])
    f.wire([(400, 205), (470, 205)])
    f.text(435, 194, "Pᵢ", anchor="middle", cls="label")
    f.wire([(640, 205), (725, 205)])
    f.text(30, 306, "Magnitude path", cls="label")
    f.box(30, 330, 145, 70, "Magnitudes", ["|Rᵢ,ⱼ| for all j"])
    f.box(235, 330, 165, 70, "Two-min tree", ["raw a₁ ≤ a₂"])
    f.box(470, 330, 170, 70, "Scale each once", ["mₖ = gₜ(aₖ)"])
    f.box(470, 430, 170, 60, "Selector", ["cᵢ,ⱼ = [|Rᵢ,ⱼ| = a₁]"])
    f.wire([(175, 365), (235, 365)])
    f.wire([(400, 365), (470, 365)])
    f.dot(420, 365)
    f.wire([(420, 365), (420, 460), (470, 460)])
    f.text(413, 424, "a₁", anchor="end", cls="label")
    f.wire([(640, 365), (725, 365)])
    f.dot(195, 365)
    f.wire([(195, 365), (195, 515), (555, 515), (555, 490)])
    f.text(355, 504, "own magnitude |Rᵢ,ⱼ|", anchor="middle", cls="small")
    f.wire([(640, 460), (725, 460)])
    f.text(797, 529, ["CNU clock edge", "enable: step.fire"], anchor="middle", cls="small")
    f.text(30, 564, ["Shared pair; one sign and selector per edge.",
                     "Ties stay duplicated: (2, 2, 5) → (2, 2)."], cls="small")
    f.parts.append(f'<path d="M 30 611 H 870" stroke="{LINE}"/>')
    f.text(30, 642, "Combinational XOR tree", cls="label")
    f.text(30, 668, "Illustrative degree-three check; gate grouping does not prescribe synthesis.", cls="small")
    # Three representative signs form a reduction; the syndrome adjusts parity.
    for x, y in ((275, 720), (455, 765), (650, 765)):
        f.parts.append(f'<circle cx="{x}" cy="{y}" r="16" fill="white" '
                       f'stroke="{BLUE}" stroke-width="1.7"/>')
        f.text(x, y + 6, "⊕", anchor="middle")
    for label, y in (("b₁", 695), ("b₂", 745), ("b₃", 795), ("stored σᵢ", 845)):
        f.text(50, y + 5, label, cls="syndrome" if label.startswith("stored") else "small")
    f.wire([(180, 695), (230, 695), (262, 710)])
    f.wire([(180, 745), (230, 745), (262, 730)])
    f.wire([(291, 720), (380, 720), (442, 755)])
    f.wire([(180, 795), (380, 795), (442, 775)])
    f.wire([(471, 765), (634, 765)])
    f.wire([(180, 845), (650, 845), (650, 781)])
    f.wire([(666, 765), (760, 765)])
    f.text(778, 771, "Pᵢ", cls="label")
    f.text(684, 807, ["Shared parity", "for every edge"], cls="small")
    return f.finish()


def vnu():
    f = Figure("vnu", "VNU: one full-width total, three outputs",
               "A VNU reconstructs each signed check message from a shared minimum pair and edge metadata. "
               "A balanced adder combines these messages with the bias. The full-width total branches "
               "to per-edge subtraction and sign-magnitude clipping, signed marginal saturation, and a "
               "strict negative comparison. On an ordinary iteration the VNU state register commits "
               "the three outputs together. At a Relay restart, the edge-message register instead "
               "reloads the immutable prior, while the new marginal and decision still commit. "
               "The own-message subtraction bypass never uses the saturated marginal.", 535)
    f.header("VNU · one total, three outputs", "Variable j · the same VariableNode serves vanilla and Relay BP")
    f.text(820, 116, "State register", anchor="middle", cls="label")
    f.box(135, 240, 155, 75, "Select + convert", ["m₁ / m₂, sign", "→ signed σᵢ,ⱼ"])
    f.box(335, 240, 170, 75, "Shared adder", ["full-width total Tⱼ"])
    f.box(585, 150, 155, 75, "Per-edge output", ["Tⱼ − own σᵢ,ⱼ", "clip + sign/mag"])
    f.box(585, 270, 155, 60, "Stored marginal", ["signed saturation"])
    f.box(585, 390, 155, 60, "Hard decision", ["Tⱼ < 0"])
    f.register(790, 140, 80, 325, [("Rᵢ,ⱼ", 188), ("Mⱼ", 300), ("êⱼ", 420)])
    f.text(30, 240, ["CNU pair", "+ metadata"], cls="small")
    f.wire([(30, 278), (135, 278)])
    f.wire([(290, 278), (335, 278)])
    f.dot(310, 278)
    f.wire([(310, 278), (310, 128), (662, 128), (662, 150)])
    f.text(480, 117, "own σᵢ,ⱼ bypass", anchor="middle", cls="small")
    f.text(420, 202, "bias Bⱼ", anchor="middle", cls="label")
    f.wire([(420, 213), (420, 240)])
    f.wire([(505, 278), (535, 278)], arrow=False)
    f.dot(535, 278)
    f.text(535, 261, "Tⱼ", anchor="middle", cls="label")
    f.wire([(535, 278), (535, 188), (585, 188)])
    f.wire([(535, 278), (535, 300), (585, 300)])
    f.wire([(535, 300), (535, 420), (585, 420)])
    f.dot(535, 300)
    for y in (188, 300, 420):
        f.wire([(740, y), (790, y)])
    f.text(30, 383, ["Bⱼ = prior for vanilla.", "Relay computes Bⱼ from", "prior + stored memory."], cls="small")
    f.text(30, 488, ["Subtract and decide before clipping the stored marginal.",
                     "Ordinary iteration shown; Relay restart reloads Rᵢ,ⱼ = +λⱼ."], cls="small")
    return f.finish()


def relay():
    f = Figure("relay-legs", "Relay BP: memory between legs",
               "A frame loads immutable positive priors, initial marginals, and coefficient integer seven. "
               "Each BP leg keeps its coefficients fixed while updating messages and marginals. A later leg "
               "retains the terminal stored marginal, restarts edge messages and local scaling, and advances "
               "the coefficient source. Converged legs offer candidates scored with quantized priors. "
               "The decoder ends at its candidate target or total leg limit.", 510)
    f.header("Relay BP · memory between legs", "Leg index ℓ is separate from iteration t inside a leg")
    f.box(30, 155, 175, 145, "Frame load", ["Mⱼ = λⱼ", "Rᵢ,ⱼ = +λⱼ", "coefficient b = 7"])
    f.box(255, 155, 235, 145, "Leg 0", ["Fixed coefficients", "BP iterations 1 … T₀", "Converge or reach budget"])
    f.box(615, 155, 255, 145, "Next leg ℓ + 1", ["New fixed coefficients", "BP iterations 1 … Tᵣ", "Converge or reach budget"])
    f.wire([(205, 226), (255, 226)])
    f.wire([(490, 226), (615, 226)])
    f.text(552, 211, "retain Mⱼ", anchor="middle", cls="label")
    f.text(552, 246, "stored memory", anchor="middle", cls="small")
    f.text(30, 115, "Initialize once", cls="label")
    f.text(615, 115, "Repeat while allowed", cls="label")
    f.text(552, 331, ["Between legs: restart R = +λ and local ramp;", "advance the coefficient source once."], anchor="middle", cls="small")
    f.box(30, 392, 840, 82, "Stop and select", [
        "Score each converged candidate with immutable quantized priors.",
        "Finish at solutionTarget or maximumLegs; keep the lowest score.",
    ], fill="#eef7f7", stroke=TEAL)
    # Candidate decisions belong to leg commits, not to the initial frame load.
    f.wire([(280, 300), (280, 392)])
    f.wire([(850, 300), (850, 392)])
    return f.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify that generated SVGs are current")
    args = parser.parse_args()
    figures = {"cnu.svg": cnu(), "vnu.svg": vnu(), "relay-legs.svg": relay()}
    stale = []
    for name, content in figures.items():
        path = DESTINATION / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(DESTINATION.parent.parent.parent)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if stale:
        print("Stale architecture figures: " + ", ".join(stale), file=sys.stderr)
        print("Run python docs/figures/build_architecture.py", file=sys.stderr)
        return 1
    print(f"Architecture figures {'verified' if args.check else 'generated'}: {len(figures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
