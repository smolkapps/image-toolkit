"""End-to-end CLI tests: drive image_toolkit.cli.main() like a real invocation
and assert on exit codes, produced files, and stderr."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from image_toolkit.cli import main


def run(argv):
    """Call the CLI entry point; return its int exit code."""
    return main(argv)


# --------------------------------------------------------------------------- #
# convert / resize / strip-exif via CLI  (priority paths)
# --------------------------------------------------------------------------- #
def test_cli_convert(make_image, tmp_path):
    src = make_image("in.png", size=(80, 40))
    out = tmp_path / "out.webp"
    rc = run(["convert", str(src), "--to", "webp", "-o", str(out)])
    assert rc == 0
    with Image.open(out) as img:
        assert img.format == "WEBP"


def test_cli_resize_max(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = tmp_path / "r.png"
    rc = run(["resize", str(src), "--max", "100", "-o", str(out)])
    assert rc == 0
    with Image.open(out) as img:
        assert img.size == (100, 50)


def test_cli_strip_exif(make_jpeg_with_exif, tmp_path):
    src = make_jpeg_with_exif("e.jpg")
    out = tmp_path / "clean.jpg"
    rc = run(["strip-exif", str(src), "-o", str(out)])
    assert rc == 0
    with Image.open(out) as img:
        assert not img.info.get("exif")
        assert len(img.getexif()) == 0


# --------------------------------------------------------------------------- #
# batch via CLI
# --------------------------------------------------------------------------- #
def test_cli_batch_resize_directory(populated_dir, tmp_path):
    outdir = tmp_path / "resized"
    rc = run(["resize", str(populated_dir), "--max", "32", "--outdir", str(outdir)])
    assert rc == 0
    produced = list(outdir.glob("*"))
    assert len(produced) == 3
    for f in produced:
        with Image.open(f) as img:
            assert max(img.size) <= 32


def test_cli_batch_recursive(populated_dir, tmp_path):
    outdir = tmp_path / "resized"
    rc = run(
        [
            "resize",
            str(populated_dir),
            "--max",
            "32",
            "--outdir",
            str(outdir),
            "--recursive",
        ]
    )
    assert rc == 0
    # 3 top-level + 1 nested mirrored under sub/
    top = list(outdir.glob("*.png")) + list(outdir.glob("*.jpg"))
    assert len(top) == 3
    assert len(list((outdir / "sub").glob("*"))) == 1


def test_cli_info(make_jpeg_with_exif, capsys):
    src = make_jpeg_with_exif("e.jpg", size=(160, 120))
    rc = run(["info", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "JPEG" in out
    assert "160x120" in out
    assert "has_exif: True" in out


def test_cli_grayscale_and_watermark(make_image, tmp_path):
    src = make_image("in.png", size=(120, 90))
    g = tmp_path / "g.png"
    assert run(["grayscale", str(src), "-o", str(g)]) == 0
    with Image.open(g) as img:
        assert img.mode == "L"

    w = tmp_path / "w.png"
    assert run(["watermark", str(src), "--text", "(C) 2026", "-o", str(w)]) == 0
    assert w.exists()


def test_cli_rotate_and_flip(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    r = tmp_path / "r.png"
    assert run(["rotate", str(src), "--degrees", "90", "-o", str(r)]) == 0
    with Image.open(r) as img:
        assert img.size == (100, 200)

    f = tmp_path / "f.png"
    assert run(["flip", str(src), "--horizontal", "-o", str(f)]) == 0
    assert f.exists()


def test_cli_thumbnail_outdir(make_image, tmp_path):
    src = make_image("in.png", size=(400, 300))
    outdir = tmp_path / "thumbs"
    assert run(["thumbnail", str(src), "--size", "100", "--outdir", str(outdir)]) == 0
    produced = list(outdir.glob("*"))
    assert len(produced) == 1
    with Image.open(produced[0]) as img:
        assert max(img.size) <= 100


# --------------------------------------------------------------------------- #
# montage via CLI
# --------------------------------------------------------------------------- #
def test_cli_montage_directory(populated_dir, tmp_path, capsys):
    out = tmp_path / "sheet.png"
    rc = run(
        [
            "montage",
            str(populated_dir),
            "--cell",
            "40",
            "--columns",
            "2",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    assert out.exists()
    assert f"wrote {out}" in capsys.readouterr().out
    with Image.open(out) as img:
        # 3 top-level images, 2 columns -> 2 rows.
        assert img.size == (8 + 2 * (40 + 8), 8 + 2 * (40 + 8))


def test_cli_montage_recursive(populated_dir, tmp_path):
    out = tmp_path / "sheet.png"
    rc = run(
        [
            "montage",
            str(populated_dir),
            "--recursive",
            "--columns",
            "4",
            "--cell",
            "20",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    with Image.open(out) as img:
        # 3 top-level + 1 nested = 4 images, one row of 4.
        assert img.size == (8 + 4 * (20 + 8), 8 + 1 * (20 + 8))


def test_cli_montage_no_inputs_nonzero(tmp_path, capsys):
    rc = run(["montage", str(tmp_path / "empty"), "-o", str(tmp_path / "s.png")])
    assert rc == 2
    assert "no matching input" in capsys.readouterr().err.lower()


# --------------------------------------------------------------------------- #
# error handling / exit codes
# --------------------------------------------------------------------------- #
def test_cli_missing_input_nonzero(tmp_path, capsys):
    rc = run(["info", str(tmp_path / "nope.png")])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no matching input" in err.lower()


def test_cli_bad_format_nonzero(make_image, tmp_path, capsys):
    src = make_image("in.png")
    rc = run(["convert", str(src), "--to", "xyz", "-o", str(tmp_path / "o.xyz")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unsupported format" in err.lower()


def test_cli_out_with_multiple_inputs_rejected(populated_dir, tmp_path, capsys):
    rc = run(
        [
            "resize",
            str(populated_dir),
            "--max",
            "32",
            "-o",
            str(tmp_path / "single.png"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "single input" in err.lower()


def test_cli_corrupt_image_reports_failure(populated_dir, tmp_path, capsys):
    (populated_dir / "broken.png").write_text("nope")
    outdir = tmp_path / "out"
    rc = run(["grayscale", str(populated_dir), "--outdir", str(outdir)])
    # 3 good + 1 bad -> partial success exit code 1
    assert rc == 1
    err = capsys.readouterr().err
    assert "broken.png" in err
    # the 3 valid images still got processed
    assert len(list(outdir.glob("*.png"))) >= 2
