# Watch BP on the Steane code

This three-minute animation follows a Steane-code sector through graph
construction, check and variable updates, vanilla BP, and Relay scheduling.

```{raw} html
<video controls preload="metadata" poster="_static/learning/steane-bp-poster.png" aria-label="Steane BP hardware walkthrough">
  <source src="_static/learning/steane-bp.mp4" type="video/mp4">
  <track kind="captions" src="_static/learning/steane-bp.vtt" srclang="en" label="English" default>
  <p><a href="_static/learning/steane-bp.mp4">Download the video</a>.</p>
</video>
```

[Video download](_static/learning/steane-bp.mp4) ·
[Transcript](_static/learning/steane-bp-transcript.txt) ·
[Captions](_static/learning/steane-bp.vtt)

| Time | Topic | Reference |
| --- | --- | --- |
| 0:00 | Matrix, graph, and fixed wiring | [Graph construction](architecture/index.md) |
| 0:26 | Syndrome and priors | [Inputs and messages](qec-background.md) |
| 0:45 | Check update | [CNU](architecture/bp-decoder.md) |
| 1:11 | Variable update | [VNU](architecture/bp-decoder.md) |
| 1:38 | Vanilla stopping | [Vanilla BP](experiments/bp-only.md) |
| 2:05 | Relay memory and leg boundaries | [Relay](architecture/relay-bp.md) |

The animation uses **quantized min-sum** with integer ramp scaling. Its internal
values come from the Scala reference and were checked against Chisel tests when
the animation was produced. They are not direct RTL waveform probes.

The first [teaching fixture](_static/learning/steane-problem.json) has priors
`[4,4,4,1,4,4,4]`. The scheduling chapters explicitly switch to a
[uniform-prior fixture](_static/learning/uniform-problem.json). These are
hand-constructed examples, not circuit-level failure-rate measurements.
Syndrome agreement alone does not establish logical success.

## Captured implementation

This is the **October 5, 2026 snapshot**. The captured hardware sources match the
publication checkout apart from two added comments in `TwoMin.scala`. The old
documentation exporter, its two test files, and original fixture path are absent.
The video preserves the captured reference traces and original verification.

The current [AnimationTraceSpec](../../src/test/scala/chipsldpc/AnimationTraceSpec.scala)
replays all eight captured iterations and final outcomes against the integer
reference: both fixtures, with vanilla and Relay BP. The check includes messages,
minima, biases, decisions, residuals, restarts, and candidate selection. It passes
for this checkout. This checks the numerical examples, not RTL waveform timing.
Run it after changing the decoder:

```sh
./mill --no-server chipsLDPC.test.testOnly chipsldpc.AnimationTraceSpec
```

The full [Steane trace](_static/learning/steane-trace.json) and
[uniform-prior trace](_static/learning/uniform-trace.json) retain their original
bytes and hashes. Use the current [hardware reference](architecture/index.md)
and [verification guide](verification.md) for hardware changes.

The bundle preserves [source provenance](_static/learning/animation-provenance.json),
[the source comparison](_static/learning/source-alignment.json), and
[the original video verification receipt](_static/learning/animation-verification.json).
The source project is `chipsldpc-manim`, storyboard `bpviz/scenes.py`. Ordinary
documentation viewing does not require Manim or the source project.

For the accompanying equations and BB144 results, see the
[QEC decoding slides](decoding-slides.md).
