# BP on the Steane code

This 52-second animation shows three rounds of sum-product BP on one Steane-code
sector: graph construction, message passing, and the final hard decision.

```{raw} html
<video controls preload="metadata" poster="_static/learning/steane-bp-poster.png" aria-label="Sum-product BP on a Steane-code sector">
  <source src="_static/learning/steane-bp.mp4" type="video/mp4">
  <track kind="captions" src="_static/learning/steane-bp.vtt" srclang="en" label="English descriptions">
  <p><a href="_static/learning/steane-bp.mp4">Download the animation</a>.</p>
</video>
```

[Download](_static/learning/steane-bp.mp4) ·
[Text description](_static/learning/steane-bp-transcript.txt) ·
[Captions](_static/learning/steane-bp.vtt)

Every variable has error prior `0.10`. An error on the third variable gives
syndrome `[1, 1, 1]`. The three rounds are fixed for illustration, without early
stopping; the final estimate recovers that error.

The animation uses floating-point **sum-product** updates. The repository's RTL
experiments use **quantized min-sum**. See the [BP background](qec-background.md)
for the equations and the [QEC decoding presentation](decoding-slides.md) for
more context.

The [source snapshot](_static/learning/sum-product-provenance.json) records the
video and source hashes. The [numerical model](_static/learning/sum-product-model.py)
and [scene source](_static/learning/sum-product-scene.py) are included; viewing
the animation needs no Manim installation.
