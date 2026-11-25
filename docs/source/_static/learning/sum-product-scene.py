from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manimlib import (
    DOWN,
    FadeIn,
    FadeOut,
    LaggedStart,
    Line,
    Scene,
    ShowCreation,
    ShowPassingFlash,
    Square,
    Tex,
    Text,
    Transform,
    UP,
    VGroup,
    WHITE,
)
from manimlib import Circle

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from bp_decoder import BPOSDDecoder, BPTraceStep, default_demo_case


FONT = "Avenir Next"
MATH_FONT = "STIX Two Text"

INK = "#17232D"
MUTED = "#65717A"
HAIRLINE = "#D8D4CC"
NAVY = "#173B53"
BLUE = "#2E6F95"
PALE_BLUE = "#DCE8F0"
TEAL = "#0A9B8E"
TEAL_DARK = "#08766E"
PALE_TEAL = "#DDEDEA"
CORAL = "#E85D42"
CORAL_PALE = "#F7DED7"

H_MAT, _, SYNDROME = default_demo_case()
DECODER = BPOSDDecoder(H_MAT, error_rate=0.10, max_iter=3)
TRACE = DECODER.trace_rounds(SYNDROME, rounds=3)


def tanner_edges(h_mat: np.ndarray) -> list[tuple[int, int]]:
    return [(int(i), int(j)) for i, j in zip(*np.nonzero(h_mat))]


def stage_title(text: str) -> Text:
    title = Text(text, font=FONT, font_size=36, weight="BOLD")
    return title.set_color(INK).to_edge(UP, buff=0.24)


def title_rule() -> VGroup:
    full = Line(
        np.array([-6.45, 2.96, 0.0]),
        np.array([6.45, 2.96, 0.0]),
    ).set_stroke(HAIRLINE, width=2)
    accent = Line(
        np.array([-6.45, 2.96, 0.0]),
        np.array([-4.85, 2.96, 0.0]),
    ).set_stroke(TEAL, width=4)
    return VGroup(full, accent)


def equation(tex: str) -> Tex:
    result = Tex(tex).set_color(NAVY).scale(0.62).move_to(UP * 2.10)
    if result.get_width() > 10.5:
        result.set_width(10.5)
    return result


def bit_vector(values: np.ndarray) -> str:
    return ", ".join(str(int(value)) for value in values)


class TannerGraph:
    """Small Manim-native Tanner graph with stable node and edge access."""

    def __init__(self, h_mat: np.ndarray):
        self.h_mat = h_mat
        self.edges = tanner_edges(h_mat)
        self.var_positions = [
            np.array([x, 0.55, 0.0]) for x in np.linspace(-5.1, 5.1, h_mat.shape[1])
        ]
        self.check_positions = [
            np.array([x, -1.10, 0.0]) for x in np.linspace(-2.5, 2.5, h_mat.shape[0])
        ]
        self.edge_lines: dict[tuple[int, int], Line] = {}
        self.var_shapes: list[Circle] = []
        self.check_shapes: list[Square] = []
        self.var_nodes: list[VGroup] = []
        self.check_nodes: list[VGroup] = []
        self.row_labels = VGroup()

    def build(self) -> VGroup:
        edge_group = VGroup()
        node_group = VGroup()

        for check_index, var_index in self.edges:
            line = Line(
                self.var_positions[var_index],
                self.check_positions[check_index],
            ).set_stroke(HAIRLINE, width=2.4)
            self.edge_lines[(check_index, var_index)] = line
            edge_group.add(line)

        for var_index, position in enumerate(self.var_positions):
            shape = Circle(radius=0.31).move_to(position)
            shape.set_fill(PALE_BLUE, opacity=1.0).set_stroke(BLUE, width=2.5)
            node = VGroup(shape)
            self.var_shapes.append(shape)
            self.var_nodes.append(node)
            node_group.add(node)

        for check_index, position in enumerate(self.check_positions):
            shape = Square(side_length=0.62).move_to(position)
            shape.set_fill(PALE_TEAL, opacity=1.0).set_stroke(TEAL, width=2.5)
            node = VGroup(shape)
            self.check_shapes.append(shape)
            self.check_nodes.append(node)
            node_group.add(node)

        variable_label = Text("Variable nodes", font=FONT, font_size=19)
        variable_label.set_color(MUTED).move_to(np.array([-6.18, 0.55, 0.0]))
        check_label = Text("Check nodes", font=FONT, font_size=21)
        check_label.set_color(MUTED).move_to(np.array([-4.25, -1.10, 0.0]))
        self.row_labels.add(variable_label, check_label)

        return VGroup(edge_group, node_group, self.row_labels)

    def message_flashes(self, phase: str) -> list[ShowPassingFlash]:
        color = BLUE if phase == "variable_to_check" else CORAL
        flashes = []
        for check_index, var_index in self.edges:
            var_position = self.var_shapes[var_index].get_center()
            check_position = self.check_shapes[check_index].get_center()
            start, end = (
                (var_position, check_position)
                if phase == "variable_to_check"
                else (check_position, var_position)
            )
            pulse = Line(start, end).set_stroke(color, width=7)
            flashes.append(ShowPassingFlash(pulse, time_width=0.55))
        return flashes

    def posterior_animations(self, step: BPTraceStep) -> list:
        animations = []
        for index, shape in enumerate(self.var_shapes):
            is_error = int(step.estimated_error[index]) == 1
            fill = CORAL_PALE if is_error else PALE_BLUE
            stroke = CORAL if is_error else BLUE
            animations.append(
                shape.animate.set_fill(fill, opacity=1.0).set_stroke(stroke, width=3)
            )
        return animations


def value_row(
    graph: TannerGraph,
    label: str,
    values: np.ndarray,
    *,
    y: float,
    formatter: str,
) -> VGroup:
    labels = VGroup()
    row_label = Text(label, font=FONT, font_size=21, weight="BOLD")
    row_label.set_color(TEAL_DARK).move_to(np.array([-6.05, y, 0.0]))
    labels.add(row_label)

    for position, value in zip(graph.var_positions, values):
        value_label = Text(
            formatter.format(float(value)),
            font=MATH_FONT,
            font_size=18,
        )
        value_label.set_color(NAVY).move_to(np.array([position[0], y, 0.0]))
        labels.add(value_label)
    return labels


def syndrome_row(graph: TannerGraph) -> VGroup:
    labels = VGroup()
    row_label = Text("Measured syndrome", font=FONT, font_size=21, weight="BOLD")
    row_label.set_color(TEAL_DARK).move_to(np.array([-4.80, -1.78, 0.0]))
    labels.add(row_label)

    for position, value in zip(graph.check_positions, SYNDROME):
        label = Text(
            str(int(value)),
            font=MATH_FONT,
            font_size=22,
            weight="BOLD",
        )
        label.set_color(CORAL if int(value) else NAVY)
        label.move_to(np.array([position[0], -1.78, 0.0]))
        labels.add(label)
    return labels


class BPTeachingScene(Scene):
    """Presentation-ready explanation of three BP rounds on the supplied H."""

    default_camera_config = {"background_color": WHITE}

    def construct(self) -> None:
        graph = TannerGraph(H_MAT)
        graph.build()

        title = stage_title("Tanner graph")
        rule = title_rule()
        h_tex = equation(
            r"H=\begin{bmatrix}"
            r"1&1&1&1&0&0&0\\"
            r"0&1&1&0&1&1&0\\"
            r"0&0&1&1&0&1&1"
            r"\end{bmatrix}"
        )

        self.add(title, rule, h_tex)
        self.wait(2.2)
        self.play(
            LaggedStart(
                *[
                    FadeIn(node)
                    for node in graph.var_nodes
                    + graph.check_nodes
                    + list(graph.row_labels)
                ],
                lag_ratio=0.08,
            ),
            run_time=1.8,
        )
        self.wait(0.8)
        for check_index in range(H_MAT.shape[0]):
            check_edges = [
                edge for edge in graph.edges if edge[0] == check_index
            ]
            self.play(
                LaggedStart(
                    *[
                        ShowCreation(graph.edge_lines[edge])
                        for edge in check_edges
                    ],
                    lag_ratio=0.16,
                ),
                run_time=1.6,
            )
            self.wait(0.65)
        self.wait(1.4)

        prior = DECODER.channel_llr
        prior_labels = value_row(
            graph,
            "Prior",
            np.full(H_MAT.shape[1], 0.10),
            y=2.30,
            formatter="{:.2f}",
        )
        llr_labels = value_row(
            graph,
            "LLR",
            np.full(H_MAT.shape[1], prior),
            y=1.64,
            formatter="{:+.2f}",
        )
        measured_syndrome = syndrome_row(graph)
        self.play(
            FadeOut(h_tex),
            FadeIn(prior_labels),
            FadeIn(llr_labels),
            FadeIn(measured_syndrome),
            run_time=1.5,
        )
        self.wait(2.2)

        first_round_title = stage_title("Variable → check · BP round 1 of 3")
        self.play(
            Transform(title, first_round_title),
            run_time=0.9,
        )
        self.wait(0.8)

        for step_index, step in enumerate(TRACE):
            phase_name = (
                "Variable → check"
                if step.phase == "variable_to_check"
                else "Check → variable"
            )
            next_title = stage_title(
                f"{phase_name} · BP round {step.iteration} of 3"
            )
            if step_index > 0:
                self.play(Transform(title, next_title), run_time=0.9)
                self.wait(0.6)

            self.play(
                LaggedStart(*graph.message_flashes(step.phase), lag_ratio=0.04),
                run_time=2.0,
            )

            if step.phase == "check_to_variable":
                posterior_labels = value_row(
                    graph,
                    "LLR",
                    step.posterior_llr,
                    y=1.64,
                    formatter="{:+.2f}",
                )
                self.play(
                    Transform(llr_labels, posterior_labels),
                    *graph.posterior_animations(step),
                    run_time=1.0,
                )
            self.wait(1.0)

        final_step = TRACE[-1]
        decision_title = stage_title("Hard decision after three BP rounds")
        decision_bits = VGroup()
        for position, bit in zip(graph.var_positions, final_step.estimated_error):
            label = Text(
                f"ê = {int(bit)}",
                font=MATH_FONT,
                font_size=18,
                weight="BOLD",
            )
            label.set_color(CORAL if int(bit) else NAVY)
            label.move_to(position + DOWN * 0.58)
            decision_bits.add(label)

        final_vector = Text(
            f"ê = [{bit_vector(final_step.estimated_error)}]",
            font=MATH_FONT,
            font_size=28,
        ).set_color(NAVY).move_to(DOWN * 2.58)
        verification = Text(
            "Hê mod 2 = s   ✓",
            font=MATH_FONT,
            font_size=25,
            weight="BOLD",
        ).set_color(TEAL_DARK).move_to(DOWN * 3.18)

        self.play(
            Transform(title, decision_title),
            FadeIn(decision_bits),
            FadeIn(final_vector),
            run_time=1.0,
        )
        self.wait(0.8)
        self.play(FadeIn(verification), run_time=0.7)
        self.wait(3.0)


SCENES_IN_ORDER = [BPTeachingScene]
