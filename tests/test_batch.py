"""Tests for input collection and batch processing over directories/globs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from image_toolkit import core
from image_toolkit.batch import collect_inputs, run_batch


# --------------------------------------------------------------------------- #
# collect_inputs
# --------------------------------------------------------------------------- #
def test_collect_single_file(make_image):
    src = make_image("one.png")
    assert collect_inputs(str(src)) == [src]


def test_collect_directory_nonrecursive_ignores_nonimages(populated_dir):
    got = collect_inputs(str(populated_dir))
    names = sorted(p.name for p in got)
    assert names == ["a.png", "b.jpg", "c.png"]  # notes.txt + nested excluded


def test_collect_directory_recursive_includes_nested(populated_dir):
    got = collect_inputs(str(populated_dir), recursive=True)
    names = sorted(p.name for p in got)
    assert names == ["a.png", "b.jpg", "c.png", "deep.png"]


def test_collect_glob(populated_dir):
    pattern = str(populated_dir / "*.png")
    got = collect_inputs(pattern)
    names = sorted(p.name for p in got)
    assert names == ["a.png", "c.png"]


def test_collect_nothing_returns_empty(tmp_path):
    assert collect_inputs(str(tmp_path / "does_not_exist")) == []


# --------------------------------------------------------------------------- #
# run_batch
# --------------------------------------------------------------------------- #
def test_batch_processes_all_into_outdir(populated_dir, tmp_path):
    inputs = collect_inputs(str(populated_dir))  # 3 images
    outdir = tmp_path / "out"

    def op(in_path, *, outdir=None, out=None):
        return core.resize(in_path, max_side=32, outdir=outdir, out=out)

    result = run_batch(inputs, op, outdir=outdir)
    assert result.failed == 0
    assert result.ok == 3
    # every output exists, lives under outdir, and is a valid image <=32 px
    produced = sorted(outdir.glob("*"))
    assert len(produced) == 3
    for f in produced:
        with Image.open(f) as img:
            assert max(img.size) <= 32


def test_batch_recursive_mirrors_subtree(populated_dir, tmp_path):
    inputs = collect_inputs(str(populated_dir), recursive=True)  # 4 images
    outdir = tmp_path / "out"

    def op(in_path, *, outdir=None, out=None):
        return core.thumbnail(in_path, 16, outdir=outdir, out=out)

    result = run_batch(inputs, op, base=populated_dir, outdir=outdir, recursive=True)
    assert result.ok == 4
    # nested image should land under out/sub/
    nested = list((outdir / "sub").glob("*"))
    assert len(nested) == 1
    with Image.open(nested[0]) as img:
        assert max(img.size) <= 16


def test_batch_single_out_honored(make_image, tmp_path):
    src = make_image("only.png", size=(200, 100))
    out = tmp_path / "explicit.png"

    def op(in_path, *, outdir=None, out=None):
        return core.resize(in_path, max_side=50, outdir=outdir, out=out)

    result = run_batch([src], op, single_out=out)
    assert result.ok == 1
    assert result.outputs[0] == out
    assert out.exists()


def test_batch_collects_failures(populated_dir, tmp_path):
    # Point one extra "input" at a corrupt file (placed OUTSIDE the scanned
    # dir so collect_inputs doesn't also enumerate it) to force a failure path.
    bad = tmp_path / "broken.png"
    bad.write_text("not an image")
    inputs = collect_inputs(str(populated_dir)) + [bad]
    outdir = tmp_path / "out"

    def op(in_path, *, outdir=None, out=None):
        return core.grayscale(in_path, outdir=outdir, out=out)

    result = run_batch(inputs, op, outdir=outdir)
    assert result.ok == 3
    assert result.failed == 1
    assert result.failures[0][0] == bad
