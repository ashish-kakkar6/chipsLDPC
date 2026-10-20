#!/usr/bin/env python3
"""Build the original Tanner-neighborhood documentation figure (stdlib only).

Run from any directory; ``--check`` checks the tracked SVG without changing it.
The figure is a schematic neighborhood, not a second definition of a code graph.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "source/_static/figures/tanner-neighborhood.svg"
NAVY = "#243b53"
BLUE = "#245b8a"
TEAL = "#007b79"
MUTED = "#526777"


def label(x: int, y: int, symbol: str, sub: str = "", sup: str = "", *, color: str = NAVY, bold: bool = False) -> str:
    weight = ' font-weight="700"' if bold else ""
    text = escape(symbol)
    if sub:
        text += f'<tspan baseline-shift="sub" font-size="16">{escape(sub)}</tspan>'
    if sup:
        text += f'<tspan baseline-shift="super" font-size="14">{escape(sup)}</tspan>'
    return f'<text x="{x}" y="{y}" text-anchor="middle" fill="{color}" font-family="serif" font-size="25"{weight}>{text}</text>'


def arrow(x1: int, y1: int, x2: int, y2: int, kind: str) -> str:
    color = BLUE if kind == "check" else TEAL
    return f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#{kind}-arrow)"/>'


def node(x: int, y: int, symbol: str, *, check: bool = False) -> str:
    if check:
        shape = f'<rect x="{x - 27}" y="{y - 27}" width="54" height="54" fill="#edf3f8" stroke="{BLUE}" stroke-width="2.5"/>'
    else:
        shape = f'<circle cx="{x}" cy="{y}" r="28" fill="#eef8f7" stroke="{TEAL}" stroke-width="2.5"/>'
    return shape + label(x, y + 8, symbol)


def render() -> str:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="460" viewBox="0 0 1100 460" role="img" aria-labelledby="title description">',
        '<title id="title">Two directions on one Tanner-graph edge</title>',
        '<desc id="description">Square check i and circular variable j exchange messages. Check i uses its syndrome and messages from the other variables j prime and j double prime to send sigma i j toward j. Variable j uses its bias and messages from other checks i prime and i double prime to send R i j toward i. Each outgoing edge message excludes the recipient. Blue arrows point from checks to variables; teal arrows point from variables to checks.</desc>',
        '<defs>',
    ]
    for name, color in (("check", BLUE), ("variable", TEAL)):
        parts.append(f'<marker id="{name}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>')
    parts.extend([
        '</defs>',
        '<rect width="1100" height="460" fill="white"/>',
        f'<text x="315" y="39" text-anchor="middle" fill="{NAVY}" font-family="sans-serif" font-size="21" font-weight="700">Check update</text>',
        f'<text x="785" y="39" text-anchor="middle" fill="{NAVY}" font-family="sans-serif" font-size="21" font-weight="700">Variable update</text>',
        # Each fan-in ends at the edge of its recipient, clear of the node label.
        arrow(125, 153, 288, 237, "variable"),
        arrow(125, 347, 288, 263, "variable"),
        arrow(973, 153, 810, 237, "check"),
        arrow(973, 347, 810, 263, "check"),
        # Separate parallel arrows make the two directions visible.
        arrow(346, 237, 756, 237, "check"),
        arrow(756, 266, 346, 266, "variable"),
        arrow(315, 108, 315, 218, "check"),
        arrow(785, 108, 785, 217, "variable"),
        label(315, 91, "σ", "i", bold=True),
        label(785, 91, "B", "j", "(t)"),
        label(202, 174, "R", "i,j′", "(t−1)", color=TEAL),
        label(202, 352, "R", "i,j″", "(t−1)", color=TEAL),
        label(900, 174, "σ", "i′,j", "(t)", color=BLUE),
        label(900, 352, "σ", "i″,j", "(t)", color=BLUE),
        label(550, 218, "σ", "i,j", "(t)", color=BLUE),
        label(550, 309, "R", "i,j", "(t)", color=TEAL),
        node(315, 250, "i", check=True),
        node(785, 250, "j"),
        node(100, 140, "j′"),
        node(100, 360, "j″"),
        node(1000, 140, "i′", check=True),
        node(1000, 360, "i″", check=True),
        f'<text x="315" y="422" text-anchor="middle" fill="{MUTED}" font-family="sans-serif" font-size="19">Use the neighbors of i other than j.</text>',
        f'<text x="785" y="422" text-anchor="middle" fill="{MUTED}" font-family="sans-serif" font-size="19">Use the neighbors of j other than i.</text>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed SVG differs from its source")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            parser.exit(1, "Tanner figure is stale: run python docs/figures/build_tanner.py\n")
        print("Tanner-neighborhood SVG matches its source.")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding="utf-8")
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
