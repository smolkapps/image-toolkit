"""Output safety regressions using only tiny generated images in tmp_path."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from image_toolkit import core
from image_toolkit.batch import run_batch
from image_toolkit.cli import main


@pytest.mark.parametrize(
    "to, expected", [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"),
                     ("gif", "GIF"), ("bmp", "BMP"), ("tiff", "TIFF")]
)
def test_new_conversion_preserves_source(make_image, tmp_path, to, expected):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    out = tmp_path / f"converted.{to}"
    assert core.convert(src, to, out) == out
    assert src.read_bytes() == before
    with Image.open(out) as image:
        assert image.format == expected
        assert image.size == (8, 6)


@pytest.mark.parametrize("default", [False, True])
def test_conversion_cannot_replace_its_source(make_image, default):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "png", None if default else src)
    assert src.read_bytes() == before


@pytest.mark.parametrize("alias", ["relative", "symlink", "hardlink", "parent-symlink"])
def test_conversion_cannot_replace_source_through_alias(make_image, tmp_path, monkeypatch, alias):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    out = tmp_path / "alias.png"
    if alias == "relative":
        monkeypatch.chdir(tmp_path)
        out = Path("./source.png")
    elif alias == "symlink":
        out.symlink_to(src)
    elif alias == "hardlink":
        os.link(src, out)
    else:
        directory = tmp_path / "linked"
        directory.symlink_to(tmp_path, target_is_directory=True)
        out = directory / "source.png"
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "jpg", out)
    assert src.read_bytes() == before
    if alias == "symlink":
        assert out.is_symlink()
    if alias == "hardlink":
        assert out.samefile(src)


def test_conversion_rejects_dangling_output_symlink(make_image, tmp_path):
    src = make_image("source.png", size=(8, 6))
    target = tmp_path / "missing.jpg"
    out = tmp_path / "alias.jpg"
    out.symlink_to(target)
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "jpg", out)
    assert out.is_symlink()
    assert not target.exists()


def test_conversion_preserves_existing_unrelated_output(make_image):
    src = make_image("source.png", size=(8, 6))
    out = make_image("existing.jpg", size=(6, 8), color=(20, 70, 180))
    before = {path: path.read_bytes() for path in (src, out)}
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "jpg", out)
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("use_outdir", [False, True])
def test_cli_batch_rejects_same_stem_before_any_write(make_image, tmp_path, capsys, use_outdir):
    sources = [make_image(f"inputs/photo.{ext}", size=(8, 6)) for ext in ("png", "bmp")]
    before = {path: path.read_bytes() for path in sources}
    outdir = tmp_path / "outputs" if use_outdir else sources[0].parent
    argv = ["convert", str(sources[0].parent), "--to", "jpg"]
    if use_outdir:
        argv += ["--outdir", str(outdir)]
    assert main(argv) == 1
    captured = capsys.readouterr()
    assert "collision" in captured.err.lower()
    assert not captured.out
    assert not (outdir / "photo.jpg").exists()
    assert {path: path.read_bytes() for path in sources} == before


def test_cli_batch_preserves_mixed_format_originals(make_image, capsys):
    sources = [make_image(f"inputs/photo.{ext}", size=(8, 6)) for ext in ("jpg", "png")]
    before = {path: path.read_bytes() for path in sources}
    assert main(["convert", str(sources[0].parent), "--to", "jpg"]) == 1
    assert "output" in capsys.readouterr().err.lower()
    assert {path: path.read_bytes() for path in sources} == before


def test_cli_batch_existing_output_aborts_before_new_outputs(make_image, tmp_path, capsys):
    sources = [make_image(f"inputs/{name}.png", size=(8, 6)) for name in ("a", "z")]
    existing = make_image("outputs/z.jpg", size=(6, 8))
    before = {path: path.read_bytes() for path in sources + [existing]}
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(existing.parent)]) == 1
    captured = capsys.readouterr()
    assert "output" in captured.err.lower()
    assert not captured.out
    assert not (existing.parent / "a.jpg").exists()
    assert {path: path.read_bytes() for path in before} == before


def test_library_batch_never_counts_one_destination_twice(make_image, tmp_path):
    sources = [make_image(f"inputs/photo.{ext}", size=(8, 6)) for ext in ("png", "bmp")]
    before = {path: path.read_bytes() for path in sources}
    outdir = tmp_path / "outputs"
    result = run_batch(sources, core.convert, outdir=outdir, op_kwargs={"to": "jpg"})
    assert result.ok == 1
    assert result.failed == 1
    assert result.outputs == [outdir / "photo.jpg"]
    assert {path: path.read_bytes() for path in sources} == before


def test_cli_batch_rejects_case_only_planned_collisions(make_image, tmp_path, capsys):
    make_image("inputs/Photo.png", size=(8, 6))
    make_image("inputs/photo.bmp", size=(8, 6))
    outdir = tmp_path / "outputs"
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(outdir)]) == 1
    assert "collision" in capsys.readouterr().err.lower()
    assert not outdir.exists()


def test_cli_recursive_batch_keeps_distinct_outputs(make_image, tmp_path):
    sources = [make_image(f"inputs/{sub}/photo.png", size=(8, 6)) for sub in ("a", "b")]
    before = {path: path.read_bytes() for path in sources}
    outdir = tmp_path / "outputs"
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(outdir), "--recursive"]) == 0
    assert sorted(path.relative_to(outdir).as_posix() for path in outdir.rglob("*.jpg")) == ["a/photo.jpg", "b/photo.jpg"]
    assert {path: path.read_bytes() for path in sources} == before


def test_cli_preflights_symlink_parent_output_aliases(make_image, tmp_path, capsys):
    make_image("inputs/a/photo.png", size=(8, 6))
    make_image("inputs/b/photo.bmp", size=(8, 6))
    outdir = tmp_path / "outputs"
    (outdir / "a").mkdir(parents=True)
    (outdir / "b").symlink_to(outdir / "a", target_is_directory=True)
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(outdir), "--recursive"]) == 1
    assert "collision" in capsys.readouterr().err.lower()
    assert not (outdir / "a" / "photo.jpg").exists()


def test_cli_preflights_output_file_directory_collision(make_image, tmp_path, capsys):
    make_image("inputs/photo.png", size=(8, 6))
    make_image("inputs/photo.jpg/child.png", size=(8, 6))
    outdir = tmp_path / "outputs"
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(outdir), "--recursive"]) == 1
    assert "collision" in capsys.readouterr().err.lower()
    assert not outdir.exists()


def test_cli_preflights_dangling_output_parent(make_image, tmp_path, capsys):
    make_image("inputs/a/photo.png", size=(8, 6))
    make_image("inputs/b/photo.bmp", size=(8, 6))
    outdir = tmp_path / "outputs"
    outdir.mkdir()
    missing = tmp_path / "missing"
    (outdir / "b").symlink_to(missing, target_is_directory=True)
    assert main(["convert", str(tmp_path / "inputs"), "--to", "jpg", "--outdir", str(outdir), "--recursive"]) == 1
    captured = capsys.readouterr()
    assert "output" in captured.err.lower()
    assert not (outdir / "a" / "photo.jpg").exists()
    assert not captured.out
    assert (outdir / "b").is_symlink()
    assert not missing.exists()


@pytest.mark.parametrize("error", [OSError, ValueError])
def test_partial_encode_failure_leaves_no_output_and_retry_succeeds(make_image, tmp_path, monkeypatch, error):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    out = tmp_path / "result.jpg"
    original_save = Image.Image.save

    def fail_after_write(self, fp, *args, **kwargs):
        if hasattr(fp, "write"):
            fp.write(b"partial image")
        else:
            Path(fp).write_bytes(b"partial image")
        raise error("synthetic encode failure")

    monkeypatch.setattr(Image.Image, "save", fail_after_write)
    with pytest.raises(core.ImageToolkitError, match="synthetic encode failure"):
        core.convert(src, "jpg", out)
    assert src.read_bytes() == before
    assert not out.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source.png"]

    monkeypatch.setattr(Image.Image, "save", original_save)
    assert core.convert(src, "jpg", out) == out
    with Image.open(out) as image:
        assert image.format == "JPEG"
    completed = out.read_bytes()
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "jpg", out)
    assert out.read_bytes() == completed
    assert src.read_bytes() == before


def test_output_appearing_during_encoding_is_preserved(make_image, tmp_path, monkeypatch):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    out = tmp_path / "result.jpg"
    original_save = Image.Image.save

    def encode_then_contend(self, fp, *args, **kwargs):
        original_save(self, fp, *args, **kwargs)
        out.write_bytes(b"another writer's output")

    monkeypatch.setattr(Image.Image, "save", encode_then_contend)
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.convert(src, "jpg", out)
    assert out.read_bytes() == b"another writer's output"
    assert src.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["result.jpg", "source.png"]


def test_cli_conversion_write_failure_is_reported(make_image, tmp_path, capsys, monkeypatch):
    src = make_image("source.png", size=(8, 6))
    out = tmp_path / "result.jpg"

    def fail_save(self, fp, *args, **kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    assert main(["convert", str(src), "--to", "jpg", "-o", str(out)]) == 1
    assert "synthetic write failure" in capsys.readouterr().err
    assert not out.exists()


def test_unsupported_atomic_publication_fails_closed(make_image, tmp_path, monkeypatch):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    out = tmp_path / "result.jpg"

    def no_links(*args, **kwargs):
        raise OSError("hard links unsupported")

    monkeypatch.setattr(core.os, "link", no_links)
    with pytest.raises(core.ImageToolkitError, match="hard links unsupported"):
        core.convert(src, "jpg", out)
    assert not out.exists()
    assert src.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source.png"]


def test_other_transforms_share_source_preservation(make_image):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.resize(src, max_side=4, out=src)
    assert src.read_bytes() == before


def test_montage_cannot_replace_a_source(make_image):
    src = make_image("source.png", size=(8, 6))
    before = src.read_bytes()
    with pytest.raises(core.ImageToolkitError, match="output"):
        core.montage([src], src, cell=8, padding=0)
    assert src.read_bytes() == before
