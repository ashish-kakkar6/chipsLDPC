#!/usr/bin/env python3
"""Publish or check the documentation animation, presentation, and reference fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/source/_static/learning"
CAPTIONS = [
    (0.0, 13.0, "A Steane-code sector: seven variables and three parity checks."),
    (13.0, 17.0, "Uniform error prior 0.10; initial LLR 2.20. Measured syndrome: [1, 1, 1]."),
    (18.4, 26.9, "BP round 1: variable-to-check messages, then check-to-variable messages."),
    (27.0, 36.9, "BP round 2 repeats the message updates using the updated LLRs."),
    (37.0, 46.9, "BP round 3 repeats the variable and check updates."),
    (48.0, 52.4, "The final estimate is [0, 0, 1, 0, 0, 0, 0]. Its syndrome matches the measurement."),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def timestamp(seconds: float) -> str:
    total = round(seconds * 1000)
    minutes, remainder = divmod(total, 60000)
    sec, milliseconds = divmod(remainder, 1000)
    return f"00:{minutes:02d}:{sec:02d}.{milliseconds:03d}"


def publish(animation: Path, presentation: Path) -> None:
    # Publishing needs pypdf and ffmpeg/ffprobe; normal builds use only stdlib.
    from pypdf import PdfReader, PdfWriter

    DEST.mkdir(parents=True, exist_ok=True)
    video = animation / "media/BPTeachingScene.mp4"
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json", str(video),
    ]))
    duration = float(info["format"]["duration"])
    if abs(duration - 52.4) > 0.05:
        raise ValueError("The descriptive captions require the reviewed 52.4-second animation")
    shutil.copyfile(video, DEST / "steane-bp.mp4")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "16",
        "-i", str(video), "-frames:v", "1", str(DEST / "steane-bp-poster.png"),
    ], check=True)
    sources = {}
    for source, target in (("bp_decoder.py", "sum-product-model.py"),
                           ("render_scenes.py", "sum-product-scene.py")):
        shutil.copyfile(animation / source, DEST / target)
        sources[source] = digest(animation / source)
    (DEST / "steane-bp.vtt").write_text("WEBVTT\n\n" + "\n\n".join(
        f"{timestamp(start)} --> {timestamp(end)}\n{text}" for start, end, text in CAPTIONS
    ) + "\n")
    (DEST / "steane-bp-transcript.txt").write_text(
        "Sum-product BP on one Steane-code sector\n\n"
        "Description of a silent, 52.4-second animation. The three rounds are fixed for illustration, "
        "without early stopping. The repository's RTL experiments use quantized min-sum.\n\n" +
        "\n".join(f"{timestamp(start)} {text}" for start, _, text in CAPTIONS) +
        "\n\nThe planted error is on v2 (zero-based numbering). The numerical model uses "
        "floating-point tanh/atanh sum-product updates. This is not a circuit-noise sample or an RTL trace.\n"
    )
    write_json(DEST / "sum-product-provenance.json", {
        "source_project": "decoder_manim",
        "source_directory": "animations/bp_rounds_demo",
        "source_asset": "media/BPTeachingScene.mp4",
        "source_sha256": sources,
        "video_sha256": digest(video),
        "duration_seconds": duration,
        "source_revision": None,
        "source_note": "Uncommitted source snapshot; no Git revision was available.",
        "semantics": "Floating-point sum-product BP; uniform error prior 0.10; three fixed rounds; no Relay or OSD phase.",
        "caption_note": "Descriptions added for documentation, checked against the rendered phases and scene timing; the video has no audio.",
    })

    # Keep the earlier integer traces solely as separate numerical regressions.
    for old, new in (("animation-provenance.json", "reference-provenance.json"),
                     ("source-alignment.json", "reference-source-alignment.json")):
        if (DEST / old).exists():
            (DEST / old).rename(DEST / new)
    for name in ("animation-verification.json", "steane-bp.srt", "steane-bp-chapters.json",
                 "qec-decoding-vtt.pdf"):
        (DEST / name).unlink(missing_ok=True)

    reader = PdfReader(presentation)
    writer = PdfWriter()
    for page in reader.pages[11:23]:
        writer.add_page(page)
    writer.add_metadata({"/Title": "QEC decoding presentation", "/Author": "Ashish Kakkar",
                         "/Subject": "QEC decoding section; original pages 12-23, with page numbering retained"})
    with (DEST / "qec-decoding-presentation.pdf").open("wb") as output:
        writer.write(output)
    write_json(DEST / "manifest.json", {
        "schema": "chipsldpc.learning-assets.v2",
        "animation": {"provenance": "sum-product-provenance.json", "duration_seconds": duration,
                      "semantics": "Sum-product teaching example, independent of the quantized RTL reference fixtures"},
        "reference_fixtures": {"provenance": "reference-provenance.json",
                               "scope": "Earlier quantized min-sum and Relay traces replayed by AnimationTraceSpec; not the displayed sum-product animation"},
        "presentation": {"source_file": presentation.name, "source_sha256": digest(presentation),
                         "original_pages": list(range(12, 24)), "pages": 12,
                         "selection": "Decoding problem, BP, Relay, hardware implementation, BB144 results"},
        "files": {p.name: digest(p) for p in sorted(DEST.iterdir()) if p.is_file() and p.name != "manifest.json"},
    })
    check()


def check() -> None:
    manifest = json.loads((DEST / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = DEST / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Learning asset missing or changed: {name}")
    provenance = json.loads((DEST / "sum-product-provenance.json").read_text())
    if digest(DEST / "steane-bp.mp4") != provenance["video_sha256"]:
        raise ValueError("Video differs from its sum-product source snapshot")
    for source, target in (("bp_decoder.py", "sum-product-model.py"),
                           ("render_scenes.py", "sum-product-scene.py")):
        if digest(DEST / target) != provenance["source_sha256"][source]:
            raise ValueError(f"Animation source snapshot differs: {target}")
    captions = (DEST / "steane-bp.vtt").read_text()
    if not captions.startswith("WEBVTT\n"):
        raise ValueError("Caption file is not WebVTT")
    for start, end, text in CAPTIONS:
        if not (0 <= start < end <= provenance["duration_seconds"]):
            raise ValueError("Caption timing exceeds the animation")
        if f"{timestamp(start)} --> {timestamp(end)}\n{text}" not in captions:
            raise ValueError("Caption text or timing differs from the reviewed description")
    reference = json.loads((DEST / "reference-provenance.json").read_text())
    for name in ("steane", "uniform"):
        if digest(DEST / f"{name}-trace.json") != reference["artifact_sha256"][f"{name}.json"]:
            raise ValueError(f"{name} trace differs from the captured integer reference")
    if manifest["presentation"]["original_pages"] != list(range(12, 24)):
        raise ValueError("Unexpected presentation page selection")
    print(f"PASS: {len(manifest['files'])} learning assets, sum-product video and captions, separate integer fixtures, and presentation manifest.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify committed assets using only the standard library")
    parser.add_argument("--publish", action="store_true", help="Copy the reviewed BP animation and extract the QEC presentation section")
    parser.add_argument("--animation", type=Path, help="Path to decoder_manim/animations/bp_rounds_demo")
    parser.add_argument("--presentation", type=Path, help="Path to the source presentation PDF")
    args = parser.parse_args()
    if args.publish:
        if not args.animation or not args.presentation:
            parser.error("--publish requires --animation and --presentation")
        publish(args.animation.resolve(), args.presentation.resolve())
    else:
        check()


if __name__ == "__main__":
    main()
