#!/usr/bin/env python3
"""Publish or check the portable documentation learning bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/source/_static/learning"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def publish(animation: Path, talk: Path) -> None:
    # pypdf is needed only when publishing a new excerpt, never for doc builds.
    from pypdf import PdfReader, PdfWriter

    DEST.mkdir(parents=True, exist_ok=True)
    copies = {
        "media/HardwareWalkthrough.mp4": "steane-bp.mp4",
        "docs/preview.png": "steane-bp-poster.png",
        "media/HardwareWalkthrough.srt": "steane-bp.srt",
        "media/HardwareWalkthrough.json": "steane-bp-chapters.json",
        "docs/verification.json": "animation-verification.json",
        "data/provenance.json": "animation-provenance.json",
        "data/steane_problem.json": "steane-problem.json",
        "data/steane.json": "steane-trace.json",
        "data/uniform.json": "uniform-trace.json",
        "data/uniform_problem.json": "uniform-problem.json",
    }
    for source, destination in copies.items():
        shutil.copyfile(animation / source, DEST / destination)
    srt = (DEST / "steane-bp.srt").read_text()
    (DEST / "steane-bp.vtt").write_text("WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt))
    chapters = json.loads((DEST / "steane-bp-chapters.json").read_text())
    transcript = ["Steane BP walkthrough", ""]
    for item in chapters["captions"]:
        minutes, seconds = divmod(int(item["start"]), 60)
        transcript.append(f"{minutes:02d}:{seconds:02d} {item['text']}")
    (DEST / "steane-bp-transcript.txt").write_text("\n".join(transcript) + "\n")

    provenance = json.loads((DEST / "animation-provenance.json").read_text())
    alignment = []
    for name, expected in provenance["source_sha256"].items():
        p = ROOT / name
        actual = digest(p) if p.is_file() else None
        alignment.append({"path": name, "captured_sha256": expected,
                          "checkout_sha256": actual,
                          "status": "missing" if actual is None else "match" if actual == expected else "changed"})
    write_json(DEST / "source-alignment.json", {
        "description": "Source comparison at publication time, not a claim about future checkouts.",
        "captured_source_head": provenance["git_head"],
        "captured_at": provenance["generated_at_utc"],
        "files": alignment,
    })

    reader = PdfReader(talk)
    writer = PdfWriter()
    # One-based source pages 12--23 contain the decoding section.
    for page in reader.pages[11:23]:
        writer.add_page(page)
    writer.add_metadata({"/Title": "QEC decoding: excerpt from the VTT talk",
                         "/Author": "Ashish Kakkar",
                         "/Subject": "Original pages 12-23; page numbering retained"})
    with (DEST / "qec-decoding-vtt.pdf").open("wb") as output:
        writer.write(output)
    manifest = {
        "schema": "chipsldpc.learning-assets.v1",
        "animation": {"source_project": "chipsldpc-manim",
                      "source_asset": "media/HardwareWalkthrough.mp4",
                      "captured_at": provenance["generated_at_utc"],
                      "source_head": provenance["git_head"],
                      "semantics": "Quantized min-sum integer reference traces checked against Chisel; no direct internal waveform probes"},
        "slides": {"source_file": talk.name, "source_sha256": digest(talk),
                   "original_pages": list(range(12, 24)), "pages": 12,
                   "selection": "Decoding problem, BP, Relay, hardware implementation, BB144 results"},
        "files": {p.name: digest(p) for p in sorted(DEST.iterdir()) if p.is_file() and p.name != "manifest.json"},
    }
    write_json(DEST / "manifest.json", manifest)
    check()


def check() -> None:
    manifest = json.loads((DEST / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = DEST / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Learning asset missing or changed: {name}")
    if not (DEST / "steane-bp.vtt").read_text().startswith("WEBVTT\n"):
        raise ValueError("Caption file is not WebVTT")
    verification = json.loads((DEST / "animation-verification.json").read_text())
    if digest(DEST / "steane-bp.mp4") != verification["sha256"]:
        raise ValueError("Video differs from its saved verification receipt")
    provenance = json.loads((DEST / "animation-provenance.json").read_text())
    for name in ("steane", "uniform"):
        if digest(DEST / f"{name}-trace.json") != provenance["artifact_sha256"][f"{name}.json"]:
            raise ValueError(f"{name} trace differs from the captured animation")
    print(f"PASS: {len(manifest['files'])} learning assets, captured animation identity, captions, and 12-page slide selection manifest.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify committed file hashes using only the standard library")
    parser.add_argument("--publish", action="store_true", help="Copy an approved animation snapshot and extract the QEC slide section")
    parser.add_argument("--animation", type=Path, help="Path to the chipsldpc-manim source project")
    parser.add_argument("--talk", type=Path, help="Path to ashish-kakkar-talk-VTT.pdf")
    args = parser.parse_args()
    if args.publish:
        if not args.animation or not args.talk:
            parser.error("--publish requires --animation and --talk")
        publish(args.animation.resolve(), args.talk.resolve())
    else:
        check()


if __name__ == "__main__":
    main()
