"""Core single-file image operations.

Each public function takes an input path, does exactly one transform, and
writes (or returns info for) an output. Functions raise the typed errors
defined here on bad input so the CLI can map them to a non-zero exit with a
clean stderr message instead of a traceback.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

PathLike = Union[str, os.PathLike]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ImageToolkitError(Exception):
    """Base class for all expected (user-facing) errors."""


class InputNotFoundError(ImageToolkitError):
    """The input path does not exist or is not a regular file."""


class UnsupportedFormatError(ImageToolkitError):
    """The requested format / extension is not something Pillow can handle,
    or the input is not a readable image."""


# --------------------------------------------------------------------------- #
# Format handling
# --------------------------------------------------------------------------- #
# Map common extension spellings to a canonical Pillow format name.
# Pillow itself keys on format names like "JPEG", "PNG", "WEBP", "TIFF".
_EXT_TO_FORMAT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "jpe": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
    "bmp": "BMP",
    "tif": "TIFF",
    "tiff": "TIFF",
    "ico": "ICO",
    "ppm": "PPM",
    "tga": "TGA",
}

# Formats that cannot hold an alpha channel; we flatten RGBA/LA/P onto a
# background before saving to these.
_NO_ALPHA_FORMATS = {"JPEG", "BMP", "PPM"}


def normalize_format(fmt: str) -> str:
    """Return the canonical Pillow format name for a user-supplied token.

    Accepts either an extension-ish token ("jpg", ".PNG", "webp") or an
    already-canonical name ("JPEG"). Raises UnsupportedFormatError otherwise.
    """
    token = fmt.strip().lower().lstrip(".")
    if token in _EXT_TO_FORMAT:
        return _EXT_TO_FORMAT[token]
    # Allow an exact (case-insensitive) Pillow format name to pass through if
    # Pillow knows how to save it.
    upper = token.upper()
    if upper in Image.SAVE:
        return upper
    raise UnsupportedFormatError(
        f"unsupported format {fmt!r}; supported: "
        + ", ".join(sorted(set(_EXT_TO_FORMAT)))
    )


def _ext_for_format(fmt: str) -> str:
    """Pick a sensible file extension for a canonical format name."""
    preferred = {
        "JPEG": "jpg",
        "PNG": "png",
        "WEBP": "webp",
        "GIF": "gif",
        "BMP": "bmp",
        "TIFF": "tiff",
        "ICO": "ico",
        "PPM": "ppm",
        "TGA": "tga",
    }
    return preferred.get(fmt, fmt.lower())


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _open(path: PathLike) -> Image.Image:
    """Open an image with friendly, typed errors."""
    p = Path(path)
    if not p.exists():
        raise InputNotFoundError(f"input not found: {p}")
    if not p.is_file():
        raise InputNotFoundError(f"input is not a file: {p}")
    try:
        img = Image.open(p)
        img.load()
        return img
    except UnidentifiedImageError as exc:
        raise UnsupportedFormatError(f"cannot identify image file: {p}") from exc
    except OSError as exc:  # truncated / unreadable
        raise UnsupportedFormatError(f"cannot read image file {p}: {exc}") from exc


def _ensure_parent(path: PathLike) -> None:
    parent = Path(path).parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def _flatten_if_needed(
    img: Image.Image, fmt: str, background=(255, 255, 255)
) -> Image.Image:
    """If saving to a format with no alpha support, composite onto a solid bg."""
    if fmt in _NO_ALPHA_FORMATS and img.mode in ("RGBA", "LA", "PA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, background)
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img


def _save(
    img: Image.Image,
    out: PathLike,
    fmt: str,
    *,
    keep_exif: bool = False,
    src: Optional[Image.Image] = None,
    **save_kwargs,
) -> Path:
    """Save ``img`` as ``fmt`` to ``out``.

    By default metadata (EXIF) is dropped because a fresh Image created by a
    transform carries no exif unless we copy it. When ``keep_exif`` is True we
    pull exif from ``src`` (the originally opened image) if present.
    """
    out = Path(out)
    _ensure_parent(out)
    img = _flatten_if_needed(img, fmt)

    if keep_exif and src is not None:
        exif = src.info.get("exif")
        if exif:
            save_kwargs.setdefault("exif", exif)

    # Reasonable quality defaults for lossy formats.
    if fmt == "JPEG":
        save_kwargs.setdefault("quality", 95)
    if fmt == "WEBP":
        save_kwargs.setdefault("quality", 90)

    img.save(out, format=fmt, **save_kwargs)
    return out


def _default_out(
    in_path: PathLike,
    suffix: str,
    *,
    fmt: Optional[str] = None,
    outdir: Optional[PathLike] = None,
) -> Path:
    """Build a default output path next to (or under outdir of) the input."""
    p = Path(in_path)
    stem = p.stem
    if fmt is not None:
        ext = _ext_for_format(fmt)
    else:
        ext = p.suffix.lstrip(".") or "png"
    name = f"{stem}{suffix}.{ext}"
    if outdir is not None:
        return Path(outdir) / name
    return p.with_name(name)


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #
@dataclass
class ImageInfo:
    path: str
    format: Optional[str]
    width: int
    height: int
    mode: str
    has_exif: bool

    @property
    def size(self) -> Tuple[int, int]:
        return (self.width, self.height)

    def __str__(self) -> str:
        return (
            f"{self.path}\n"
            f"  format:   {self.format}\n"
            f"  size:     {self.width}x{self.height}\n"
            f"  mode:     {self.mode}\n"
            f"  has_exif: {self.has_exif}"
        )


def info(in_path: PathLike) -> ImageInfo:
    """Return format / size / mode / has-exif for an image."""
    img = _open(in_path)
    exif = img.info.get("exif")
    has_exif = bool(exif)
    # Some formats expose exif via getexif() even without raw bytes.
    if not has_exif:
        try:
            has_exif = len(img.getexif()) > 0
        except Exception:  # pragma: no cover - defensive
            has_exif = False
    return ImageInfo(
        path=str(Path(in_path)),
        format=img.format,
        width=img.width,
        height=img.height,
        mode=img.mode,
        has_exif=has_exif,
    )


# --------------------------------------------------------------------------- #
# convert
# --------------------------------------------------------------------------- #
def convert(
    in_path: PathLike,
    to: str,
    out: Optional[PathLike] = None,
    *,
    outdir: Optional[PathLike] = None,
    keep_exif: bool = True,
) -> Path:
    """Convert an image to a different format.

    ``to`` is an extension-ish token or canonical format name. If ``out`` is
    None a sibling file (or one under ``outdir``) named ``<stem>.<ext>`` is used.
    EXIF is preserved by default (use strip-exif to remove it).
    """
    fmt = normalize_format(to)
    src = _open(in_path)
    if out is None:
        out = _default_out(in_path, suffix="", fmt=fmt, outdir=outdir)
    # convert() with no mode change still gives us a detached copy to save.
    img = src.copy()
    return _save(img, out, fmt, keep_exif=keep_exif, src=src)


# --------------------------------------------------------------------------- #
# resize
# --------------------------------------------------------------------------- #
def _resized_dims(
    w: int,
    h: int,
    *,
    max_side: Optional[int],
    width: Optional[int],
    height: Optional[int],
    percent: Optional[float],
) -> Tuple[int, int]:
    if max_side is not None:
        if max_side <= 0:
            raise ImageToolkitError("--max must be a positive integer")
        longest = max(w, h)
        if longest <= max_side:
            return (w, h)  # never upscale on --max
        scale = max_side / float(longest)
        return (max(1, round(w * scale)), max(1, round(h * scale)))

    if percent is not None:
        if percent <= 0:
            raise ImageToolkitError("--percent must be a positive number")
        scale = percent / 100.0
        return (max(1, round(w * scale)), max(1, round(h * scale)))

    if width is not None or height is not None:
        if width is not None and height is not None:
            return (max(1, width), max(1, height))
        # one dimension given: preserve aspect from the other
        if width is not None:
            if width <= 0:
                raise ImageToolkitError("--width must be positive")
            scale = width / float(w)
            return (max(1, width), max(1, round(h * scale)))
        else:
            assert height is not None
            if height <= 0:
                raise ImageToolkitError("--height must be positive")
            scale = height / float(h)
            return (max(1, round(w * scale)), max(1, height))

    raise ImageToolkitError(
        "resize needs one of: --max, --percent, or --width/--height"
    )


def resize(
    in_path: PathLike,
    *,
    max_side: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    percent: Optional[float] = None,
    out: Optional[PathLike] = None,
    outdir: Optional[PathLike] = None,
    keep_exif: bool = True,
) -> Path:
    """Resize an image.

    Exactly one sizing mode should be supplied:
      * ``max_side`` — scale so the longest side == max_side (never upscale),
      * ``percent`` — scale by a percentage,
      * ``width`` and/or ``height`` — explicit dims; if only one is given the
        other is derived to preserve aspect ratio.
    """
    src = _open(in_path)
    new_dims = _resized_dims(
        src.width,
        src.height,
        max_side=max_side,
        width=width,
        height=height,
        percent=percent,
    )
    img = src.resize(new_dims, Image.LANCZOS)
    if out is None:
        out = _default_out(in_path, suffix="_resized", outdir=outdir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    return _save(img, out, fmt, keep_exif=keep_exif, src=src)


# --------------------------------------------------------------------------- #
# strip-exif
# --------------------------------------------------------------------------- #
def strip_exif(
    in_path: PathLike,
    out: Optional[PathLike] = None,
    *,
    outdir: Optional[PathLike] = None,
) -> Path:
    """Write a copy of the image with all metadata removed.

    We rebuild the image from raw pixel data so no info dict (exif, icc,
    comments, XMP) survives.
    """
    src = _open(in_path)
    # Reconstruct from raw pixel bytes only -> a fresh image whose empty
    # ``info`` dict carries no exif/icc/comments/XMP. ``frombytes`` round-trips
    # the pixel buffer without the deprecated getdata/putdata pair.
    clean = Image.frombytes(src.mode, src.size, src.tobytes())
    if out is None:
        out = _default_out(in_path, suffix="_noexif", outdir=outdir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    # keep_exif=False (default) — explicitly do not re-add metadata.
    return _save(clean, out, fmt, keep_exif=False)


# --------------------------------------------------------------------------- #
# rotate / flip
# --------------------------------------------------------------------------- #
def rotate(
    in_path: PathLike,
    degrees: float,
    out: Optional[PathLike] = None,
    *,
    outdir: Optional[PathLike] = None,
    expand: bool = True,
    keep_exif: bool = True,
) -> Path:
    """Rotate counter-clockwise by ``degrees``. ``expand`` grows the canvas so
    nothing is clipped (default True)."""
    src = _open(in_path)
    img = src.rotate(degrees, expand=expand, resample=Image.BICUBIC)
    if out is None:
        out = _default_out(in_path, suffix="_rotated", outdir=outdir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    return _save(img, out, fmt, keep_exif=keep_exif, src=src)


def flip(
    in_path: PathLike,
    *,
    horizontal: bool = False,
    vertical: bool = False,
    out: Optional[PathLike] = None,
    outdir: Optional[PathLike] = None,
    keep_exif: bool = True,
) -> Path:
    """Mirror the image horizontally and/or vertically."""
    if not (horizontal or vertical):
        raise ImageToolkitError("flip needs --horizontal and/or --vertical")
    src = _open(in_path)
    img = src
    if horizontal:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if vertical:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if out is None:
        out = _default_out(in_path, suffix="_flipped", outdir=outdir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    return _save(img, out, fmt, keep_exif=keep_exif, src=src)


# --------------------------------------------------------------------------- #
# thumbnail
# --------------------------------------------------------------------------- #
def thumbnail(
    in_path: PathLike,
    size: int,
    *,
    outdir: Optional[PathLike] = None,
    out: Optional[PathLike] = None,
) -> Path:
    """Create a thumbnail whose longest side <= ``size`` (never upscales)."""
    if size <= 0:
        raise ImageToolkitError("--size must be a positive integer")
    src = _open(in_path)
    img = src.copy()
    img.thumbnail((size, size), Image.LANCZOS)
    if out is None:
        target_dir = outdir if outdir is not None else Path(in_path).parent
        out = _default_out(in_path, suffix="_thumb", outdir=target_dir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    # Thumbnails generally don't need original metadata.
    return _save(img, out, fmt, keep_exif=False)


# --------------------------------------------------------------------------- #
# grayscale
# --------------------------------------------------------------------------- #
def grayscale(
    in_path: PathLike,
    out: Optional[PathLike] = None,
    *,
    outdir: Optional[PathLike] = None,
    keep_exif: bool = True,
) -> Path:
    """Convert to single-channel grayscale (mode 'L')."""
    src = _open(in_path)
    img = src.convert("L")
    if out is None:
        out = _default_out(in_path, suffix="_gray", outdir=outdir)
    fmt = src.format or normalize_format(Path(out).suffix or "png")
    return _save(img, out, fmt, keep_exif=keep_exif, src=src)


# --------------------------------------------------------------------------- #
# watermark
# --------------------------------------------------------------------------- #
_POSITIONS = {
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
}


def _load_font(size: int) -> ImageFont.ImageFont:
    """Best-effort scalable font; falls back to Pillow's bitmap default."""
    candidates = [
        "DejaVuSans.ttf",  # bundled with Pillow on most platforms
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _text_size(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
) -> Tuple[int, int]:
    # textbbox is the modern API (Pillow >= 8); fall back if missing.
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return (r - l, b - t)
    except AttributeError:  # pragma: no cover
        return draw.textsize(text, font=font)


def watermark(
    in_path: PathLike,
    text: str,
    *,
    position: str = "bottom-right",
    opacity: float = 0.5,
    out: Optional[PathLike] = None,
    outdir: Optional[PathLike] = None,
    font_size: Optional[int] = None,
    keep_exif: bool = True,
) -> Path:
    """Draw a semi-transparent text watermark.

    ``position`` is one of top-left/top-right/bottom-left/bottom-right/center.
    ``opacity`` is 0..1 (1 = fully opaque).
    """
    if position not in _POSITIONS:
        raise ImageToolkitError(
            f"invalid position {position!r}; choose from "
            + ", ".join(sorted(_POSITIONS))
        )
    if not (0.0 <= opacity <= 1.0):
        raise ImageToolkitError("--opacity must be between 0 and 1")
    if not text:
        raise ImageToolkitError("watermark text must not be empty")

    src = _open(in_path)
    base = src.convert("RGBA")

    if font_size is None:
        # Scale the font to the image: ~5% of the shorter side, min 12px.
        font_size = max(12, int(min(base.size) * 0.05))
    font = _load_font(font_size)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    tw, th = _text_size(draw, text, font)

    margin = max(4, int(min(base.size) * 0.02))
    w, h = base.size
    if position == "top-left":
        xy = (margin, margin)
    elif position == "top-right":
        xy = (w - tw - margin, margin)
    elif position == "bottom-left":
        xy = (margin, h - th - margin)
    elif position == "center":
        xy = ((w - tw) // 2, (h - th) // 2)
    else:  # bottom-right
        xy = (w - tw - margin, h - th - margin)

    alpha = int(round(255 * opacity))
    # White text with a thin dark stroke so it reads on any background.
    draw.text(
        xy,
        text,
        font=font,
        fill=(255, 255, 255, alpha),
        stroke_width=max(1, font_size // 16),
        stroke_fill=(0, 0, 0, alpha),
    )

    composited = Image.alpha_composite(base, overlay)

    if out is None:
        out = _default_out(in_path, suffix="_wm", outdir=outdir)

    fmt = src.format or normalize_format(Path(out).suffix or "png")
    # Flatten back if the target can't hold alpha.
    if fmt in _NO_ALPHA_FORMATS:
        final = composited.convert("RGB")
    else:
        final = composited
    return _save(final, out, fmt, keep_exif=keep_exif, src=src)


# --------------------------------------------------------------------------- #
# montage (contact sheet)
# --------------------------------------------------------------------------- #
def _parse_color(value) -> Tuple[int, int, int]:
    """Accept an (r, g, b) tuple, a #RRGGBB / #RGB hex string, or a name."""
    if isinstance(value, tuple):
        return value
    s = str(value).strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                pass
        raise ImageToolkitError(f"invalid hex color {value!r}")
    # Fall back to Pillow's named-color table (e.g. "white", "black").
    try:
        from PIL import ImageColor

        return ImageColor.getrgb(s)
    except (ValueError, ImportError) as exc:
        raise ImageToolkitError(f"invalid color {value!r}") from exc


def montage(
    in_paths,
    out: PathLike,
    *,
    columns: Optional[int] = None,
    cell: int = 200,
    padding: int = 8,
    background="#ffffff",
) -> Path:
    """Arrange many images into a single contact-sheet grid.

    Each input is thumbnailed to fit within a ``cell`` x ``cell`` box (never
    upscaled) and centered in its grid slot. Unreadable inputs are skipped; at
    least one input must be a valid image. If ``columns`` is None a near-square
    grid is chosen automatically. ``background`` may be an (r, g, b) tuple, a
    ``#RRGGBB`` hex string, or a color name.
    """
    if cell <= 0:
        raise ImageToolkitError("--cell must be a positive integer")
    if padding < 0:
        raise ImageToolkitError("--padding must be zero or positive")

    paths = [Path(p) for p in in_paths]
    if not paths:
        raise ImageToolkitError("montage needs at least one input image")

    bg = _parse_color(background)

    thumbs = []
    for p in paths:
        try:
            src = _open(p)
        except UnsupportedFormatError:
            continue  # skip anything we can't decode; keep the sheet going
        thumb = src.convert("RGBA")
        thumb.thumbnail((cell, cell), Image.LANCZOS)
        thumbs.append(thumb)

    if not thumbs:
        raise ImageToolkitError("no readable images to build a montage from")

    n = len(thumbs)
    if columns is None:
        columns = max(1, int(math.ceil(math.sqrt(n))))
    else:
        if columns <= 0:
            raise ImageToolkitError("--columns must be a positive integer")
        columns = min(columns, n)
    rows = int(math.ceil(n / columns))

    sheet_w = padding + columns * (cell + padding)
    sheet_h = padding + rows * (cell + padding)
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)

    for idx, thumb in enumerate(thumbs):
        row, col = divmod(idx, columns)
        cell_x = padding + col * (cell + padding)
        cell_y = padding + row * (cell + padding)
        # Center the (possibly smaller) thumbnail within its cell.
        off_x = cell_x + (cell - thumb.width) // 2
        off_y = cell_y + (cell - thumb.height) // 2
        sheet.paste(thumb, (off_x, off_y), mask=thumb.split()[-1])

    fmt = normalize_format(Path(out).suffix or "png")
    return _save(sheet, out, fmt, keep_exif=False)
