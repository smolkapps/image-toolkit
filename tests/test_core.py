"""Library-level tests for each single-file operation.

Priority order matches the build approach: convert, resize, strip-exif first,
then rotate/flip/thumbnail/grayscale/watermark/info and error handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from image_toolkit import core
from image_toolkit.core import (
    InputNotFoundError,
    UnsupportedFormatError,
    ImageToolkitError,
)


def _has_exif(path: Path) -> bool:
    img = Image.open(path)
    if img.info.get("exif"):
        return True
    try:
        return len(img.getexif()) > 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# convert  (PRIORITY)
# --------------------------------------------------------------------------- #
def test_convert_changes_format_and_opens(make_image, tmp_path):
    src = make_image("in.png", size=(100, 60))
    out = tmp_path / "out.jpg"
    res = core.convert(src, "jpg", out)
    assert res == out
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert img.size == (100, 60)


def test_convert_to_webp(make_image, tmp_path):
    src = make_image("in.png")
    out = core.convert(src, "webp", tmp_path / "out.webp")
    with Image.open(out) as img:
        assert img.format == "WEBP"


def test_convert_default_output_name(make_image):
    src = make_image("pic.png", size=(40, 40))
    out = core.convert(src, "jpg")  # no explicit out
    assert out.name == "pic.jpg"
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "JPEG"


def test_convert_rgba_to_jpeg_flattens(make_image, tmp_path):
    # RGBA source -> JPEG must not raise (alpha flattened to white bg)
    src = make_image("rgba.png", mode="RGBA")
    out = core.convert(src, "jpg", tmp_path / "flat.jpg")
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"


def test_convert_unsupported_format_raises(make_image):
    src = make_image("in.png")
    with pytest.raises(UnsupportedFormatError):
        core.convert(src, "xyz", "out.xyz")


# --------------------------------------------------------------------------- #
# resize  (PRIORITY)
# --------------------------------------------------------------------------- #
def test_resize_max_longest_side_preserves_aspect(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))  # 2:1
    out = core.resize(src, max_side=100, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert max(img.size) == 100
        assert img.size == (100, 50)  # aspect preserved


def test_resize_max_never_upscales(make_image, tmp_path):
    src = make_image("small.png", size=(50, 30))
    out = core.resize(src, max_side=1000, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert img.size == (50, 30)  # unchanged


def test_resize_percent(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.resize(src, percent=50, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert img.size == (100, 50)


def test_resize_width_only_preserves_aspect(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.resize(src, width=100, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert img.size == (100, 50)


def test_resize_height_only_preserves_aspect(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.resize(src, height=50, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert img.size == (100, 50)


def test_resize_width_and_height_exact(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.resize(src, width=123, height=45, out=tmp_path / "r.png")
    with Image.open(out) as img:
        assert img.size == (123, 45)


def test_resize_requires_a_mode(make_image):
    src = make_image("in.png")
    with pytest.raises(ImageToolkitError):
        core.resize(src)  # no sizing args


def test_resize_rejects_nonpositive_max(make_image):
    src = make_image("in.png")
    with pytest.raises(ImageToolkitError):
        core.resize(src, max_side=0)


# --------------------------------------------------------------------------- #
# strip-exif  (PRIORITY)
# --------------------------------------------------------------------------- #
def test_strip_exif_removes_metadata(make_jpeg_with_exif, tmp_path):
    src = make_jpeg_with_exif("exif.jpg")
    assert _has_exif(src), "fixture should carry EXIF before stripping"
    out = core.strip_exif(src, tmp_path / "clean.jpg")
    assert out.exists()
    assert not _has_exif(out)


def test_strip_exif_preserves_pixels_and_size(make_jpeg_with_exif, tmp_path):
    src = make_jpeg_with_exif("exif.jpg", size=(160, 120))
    out = core.strip_exif(src, tmp_path / "clean.jpg")
    with Image.open(out) as img:
        assert img.size == (160, 120)
        assert img.mode == "RGB"


def test_strip_exif_default_output_name(make_jpeg_with_exif):
    src = make_jpeg_with_exif("photo.jpg")
    out = core.strip_exif(src)
    assert out.name == "photo_noexif.jpg"
    assert not _has_exif(out)


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #
def test_info_reports_fields(make_image):
    src = make_image("in.png", size=(120, 80))
    meta = core.info(src)
    assert meta.format == "PNG"
    assert meta.size == (120, 80)
    assert meta.mode == "RGB"
    assert meta.has_exif is False


def test_info_detects_exif(make_jpeg_with_exif):
    src = make_jpeg_with_exif("e.jpg")
    meta = core.info(src)
    assert meta.format == "JPEG"
    assert meta.has_exif is True


# --------------------------------------------------------------------------- #
# rotate / flip
# --------------------------------------------------------------------------- #
def test_rotate_90_swaps_dims_with_expand(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.rotate(src, 90, tmp_path / "rot.png")
    with Image.open(out) as img:
        assert img.size == (100, 200)


def test_rotate_no_expand_keeps_size(make_image, tmp_path):
    src = make_image("in.png", size=(200, 100))
    out = core.rotate(src, 90, tmp_path / "rot.png", expand=False)
    with Image.open(out) as img:
        assert img.size == (200, 100)


def test_flip_horizontal_changes_pixels(make_image, tmp_path):
    src = make_image("in.png", size=(120, 80))
    before = Image.open(src).convert("RGB")
    out = core.flip(src, horizontal=True, out=tmp_path / "f.png")
    after = Image.open(out).convert("RGB")
    assert before.size == after.size
    assert before.tobytes() != after.tobytes()
    # flipping back must restore the original pixels
    assert after.transpose(Image.FLIP_LEFT_RIGHT).tobytes() == before.tobytes()


def test_flip_requires_a_direction(make_image):
    src = make_image("in.png")
    with pytest.raises(ImageToolkitError):
        core.flip(src)


# --------------------------------------------------------------------------- #
# thumbnail
# --------------------------------------------------------------------------- #
def test_thumbnail_within_size(make_image, tmp_path):
    src = make_image("in.png", size=(400, 300))
    outdir = tmp_path / "thumbs"
    out = core.thumbnail(src, 100, outdir=outdir)
    assert out.parent == outdir
    with Image.open(out) as img:
        assert max(img.size) <= 100
        # aspect preserved: 400x300 -> 100x75
        assert img.size == (100, 75)


def test_thumbnail_never_upscales(make_image, tmp_path):
    src = make_image("in.png", size=(40, 30))
    out = core.thumbnail(src, 200, outdir=tmp_path / "t")
    with Image.open(out) as img:
        assert img.size == (40, 30)


# --------------------------------------------------------------------------- #
# grayscale
# --------------------------------------------------------------------------- #
def test_grayscale_mode_L(make_image, tmp_path):
    src = make_image("in.png", size=(80, 60))
    out = core.grayscale(src, tmp_path / "g.png")
    with Image.open(out) as img:
        assert img.mode == "L"
        assert img.size == (80, 60)


# --------------------------------------------------------------------------- #
# watermark
# --------------------------------------------------------------------------- #
def _corner_box(size, position, frac=0.4):
    """Return a crop box (l, t, r, b) for the given corner of an image."""
    w, h = size
    bw, bh = int(w * frac), int(h * frac)
    if position == "bottom-right":
        return (w - bw, h - bh, w, h)
    if position == "top-left":
        return (0, 0, bw, bh)
    if position == "center":
        return ((w - bw) // 2, (h - bh) // 2, (w + bw) // 2, (h + bh) // 2)
    raise ValueError(position)


def test_watermark_changes_target_corner(make_image, tmp_path):
    src = make_image("in.png", size=(300, 200))
    before = Image.open(src).convert("RGB")
    out = core.watermark(
        src,
        "(C) 2026",
        position="bottom-right",
        opacity=0.9,
        out=tmp_path / "wm.png",
    )
    after = Image.open(out).convert("RGB")
    assert before.size == after.size

    box = _corner_box(before.size, "bottom-right")
    b_corner = before.crop(box).tobytes()
    a_corner = after.crop(box).tobytes()
    assert b_corner != a_corner, "watermark should alter the bottom-right corner"

    # And the opposite (top-left, minus our dark block region) should be largely
    # untouched — sanity that we didn't repaint the whole image.
    # Use top-right corner which has no painted block in the fixture.
    w, h = before.size
    tr = (int(w * 0.6), 0, w, int(h * 0.4))
    assert before.crop(tr).tobytes() == after.crop(tr).tobytes()


def test_watermark_center_changes_center(make_image, tmp_path):
    src = make_image("in.png", size=(300, 200))
    before = Image.open(src).convert("RGB")
    out = core.watermark(
        src, "MARK", position="center", opacity=0.8, out=tmp_path / "wm.png"
    )
    after = Image.open(out).convert("RGB")
    box = _corner_box(before.size, "center")
    assert before.crop(box).tobytes() != after.crop(box).tobytes()


def test_watermark_rejects_bad_position(make_image):
    src = make_image("in.png")
    with pytest.raises(ImageToolkitError):
        core.watermark(src, "x", position="middle")


def test_watermark_rejects_bad_opacity(make_image):
    src = make_image("in.png")
    with pytest.raises(ImageToolkitError):
        core.watermark(src, "x", opacity=5)


# --------------------------------------------------------------------------- #
# montage (contact sheet)
# --------------------------------------------------------------------------- #
def test_montage_default_grid_dimensions(make_image, tmp_path):
    # 4 images, cell 50, padding 10 -> auto 2x2 grid.
    srcs = [make_image(f"m{i}.png", size=(80, 40)) for i in range(4)]
    out = core.montage(srcs, tmp_path / "sheet.png", cell=50, padding=10)
    assert out.exists()
    with Image.open(out) as img:
        # width = padding + cols*(cell+padding); cols=rows=2
        assert img.size == (10 + 2 * (50 + 10), 10 + 2 * (50 + 10))
        assert img.mode == "RGB"


def test_montage_explicit_columns(make_image, tmp_path):
    # 5 images in 5 columns -> a single row.
    srcs = [make_image(f"m{i}.png", size=(40, 40)) for i in range(5)]
    out = core.montage(srcs, tmp_path / "sheet.png", columns=5, cell=30, padding=5)
    with Image.open(out) as img:
        assert img.size == (5 + 5 * (30 + 5), 5 + 1 * (30 + 5))


def test_montage_never_upscales_thumbnails(make_image, tmp_path):
    # A tiny source must not be blown up to fill the cell.
    src = make_image("tiny.png", size=(20, 10))
    out = core.montage([src], tmp_path / "sheet.png", cell=200, padding=0)
    # background is white; the pasted thumb stays 20x10, so most of the
    # 200x200 sheet remains white.
    with Image.open(out).convert("RGB") as img:
        assert img.size == (200, 200)
        assert img.getpixel((199, 199)) == (255, 255, 255)


def test_montage_background_color(make_image, tmp_path):
    src = make_image("a.png", size=(10, 10))
    out = core.montage(
        [src], tmp_path / "sheet.png", cell=40, padding=5, background="#ff0000"
    )
    with Image.open(out).convert("RGB") as img:
        # A padding pixel in the corner is pure background.
        assert img.getpixel((0, 0)) == (255, 0, 0)


def test_montage_skips_unreadable_inputs(make_image, tmp_path):
    good = make_image("good.png", size=(30, 30))
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    out = core.montage([good, bad], tmp_path / "sheet.png", cell=30, padding=0)
    # Only the one readable image counts -> a 1x1 grid, 30x30.
    with Image.open(out) as img:
        assert img.size == (30, 30)


def test_montage_empty_inputs_raises(tmp_path):
    with pytest.raises(ImageToolkitError):
        core.montage([], tmp_path / "sheet.png")


def test_montage_all_unreadable_raises(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("nope")
    with pytest.raises(ImageToolkitError):
        core.montage([bad], tmp_path / "sheet.png")


def test_montage_rejects_bad_cell(make_image, tmp_path):
    src = make_image("a.png")
    with pytest.raises(ImageToolkitError):
        core.montage([src], tmp_path / "sheet.png", cell=0)


# --------------------------------------------------------------------------- #
# error handling shared across ops
# --------------------------------------------------------------------------- #
def test_missing_input_raises(tmp_path):
    with pytest.raises(InputNotFoundError):
        core.info(tmp_path / "nope.png")


def test_non_image_input_raises(tmp_path):
    bogus = tmp_path / "fake.png"
    bogus.write_text("this is definitely not a PNG")
    with pytest.raises(UnsupportedFormatError):
        core.info(bogus)
