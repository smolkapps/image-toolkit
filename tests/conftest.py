"""Shared pytest fixtures: programmatically build test images with Pillow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


def _make_rgb(width: int = 120, height: int = 80, color=(200, 30, 30)) -> Image.Image:
    """A solid RGB image with a contrasting dark block in the top-left corner
    so geometric transforms (flip/rotate) and corner watermarks produce a
    detectable pixel difference."""
    img = Image.new("RGB", (width, height), color)
    block = Image.new("RGB", (max(1, width // 3), max(1, height // 3)), (10, 10, 10))
    img.paste(block, (0, 0))
    return img


def _write_image(
    path: Path,
    *,
    size=(120, 80),
    color=(200, 30, 30),
    mode: str = "RGB",
    exif: bool = False,
) -> Path:
    """Create an image file at ``path`` and return it."""
    w, h = size
    img = _make_rgb(w, h, color)
    if mode != "RGB":
        img = img.convert(mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {}
    if exif:
        exif_obj = Image.Exif()
        exif_obj[0x010F] = "image-toolkit-tests"  # Make
        exif_obj[0x0110] = "SyntheticCamera"  # Model
        save_kwargs["exif"] = exif_obj.tobytes()
    img.save(path, **save_kwargs)
    return path


@pytest.fixture
def make_image(tmp_path):
    """Factory: create an image file under tmp_path and return its Path.

    Usage: ``p = make_image("a.png", size=(120, 80), exif=True)``
    """

    def _factory(
        name: str = "img.png",
        *,
        size=(120, 80),
        color=(200, 30, 30),
        mode: str = "RGB",
        exif: bool = False,
    ) -> Path:
        return _write_image(
            tmp_path / name, size=size, color=color, mode=mode, exif=exif
        )

    return _factory


@pytest.fixture
def make_jpeg_with_exif(make_image):
    """Convenience: a JPEG that definitely carries EXIF bytes."""

    def _factory(name: str = "exif.jpg", *, size=(160, 120)) -> Path:
        return make_image(name, size=size, exif=True)

    return _factory


@pytest.fixture
def populated_dir(tmp_path):
    """A directory with several images (mixed formats), a non-image file, and a
    nested subdir holding one more image — for batch / recursive tests."""
    d = tmp_path / "photos"
    _write_image(d / "a.png", size=(120, 80))
    _write_image(d / "b.jpg", size=(200, 100))
    _write_image(d / "c.png", size=(64, 64))
    (d / "notes.txt").write_text("not an image")
    _write_image(d / "sub" / "deep.png", size=(90, 90))
    return d
