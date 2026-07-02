"""argparse-based command-line interface for image-toolkit.

Thin layer: parse args, resolve inputs, dispatch to the library, print a
summary. All real work lives in :mod:`image_toolkit.core` /
:mod:`image_toolkit.batch`. Bad input -> message on stderr + non-zero exit.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__, core
from .batch import BatchResult, collect_inputs, run_batch
from .core import ImageToolkitError


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _err(msg: str) -> None:
    print(f"image-toolkit: error: {msg}", file=sys.stderr)


def _resolve_base(inp: str) -> Optional[Path]:
    """The directory we mirror from in recursive mode, if INPUT is a dir."""
    p = Path(inp)
    if p.is_dir():
        return p
    return None


def _report(result: BatchResult) -> int:
    """Print a per-run summary; return process exit code."""
    for out in result.outputs:
        print(f"wrote {out}")
    for path, msg in result.failures:
        _err(f"{path}: {msg}")
    if not result.inputs:
        _err("no matching input images")
        return 2
    if result.failed and not result.outputs:
        return 1
    if result.failed:
        # Partial success: still signal a problem occurred.
        return 1
    return 0


def _dispatch(
    args, op, op_kwargs: dict, *, allow_out: bool = True, allow_outdir: bool = True
) -> int:
    """Common path: collect inputs, run the op over them, report."""
    recursive = getattr(args, "recursive", False)
    inputs = collect_inputs(args.input, recursive=recursive)
    if not inputs:
        _err(f"no matching input images for {args.input!r}")
        return 2

    out = getattr(args, "out", None) if allow_out else None
    outdir = getattr(args, "outdir", None) if allow_outdir else None

    if out is not None and len(inputs) > 1:
        _err("-o/--out is only valid for a single input; use --outdir for batches")
        return 2

    base = _resolve_base(args.input)
    single_out = Path(out) if out is not None else None
    outdir_path = Path(outdir) if outdir is not None else None

    result = run_batch(
        inputs,
        op,
        base=base,
        outdir=outdir_path,
        recursive=recursive,
        op_kwargs=op_kwargs,
        single_out=single_out,
    )
    return _report(result)


# --------------------------------------------------------------------------- #
# subcommand handlers
# --------------------------------------------------------------------------- #
def cmd_convert(args) -> int:
    op = partial(core.convert, to=args.to)
    return _dispatch(args, op, {})


def cmd_resize(args) -> int:
    op_kwargs = dict(
        max_side=args.max,
        width=args.width,
        height=args.height,
        percent=args.percent,
    )
    return _dispatch(args, core.resize, op_kwargs)


def cmd_strip_exif(args) -> int:
    return _dispatch(args, core.strip_exif, {})


def cmd_rotate(args) -> int:
    op = partial(core.rotate, degrees=args.degrees, expand=not args.no_expand)
    return _dispatch(args, op, {})


def cmd_flip(args) -> int:
    if not (args.horizontal or args.vertical):
        _err("flip needs --horizontal and/or --vertical")
        return 2
    op_kwargs = dict(horizontal=args.horizontal, vertical=args.vertical)
    return _dispatch(args, core.flip, op_kwargs)


def cmd_thumbnail(args) -> int:
    # thumbnail defaults its outdir to the input's dir; honor --outdir if given.
    op = partial(core.thumbnail, size=args.size)
    return _dispatch(args, op, {})


def cmd_grayscale(args) -> int:
    return _dispatch(args, core.grayscale, {})


def cmd_watermark(args) -> int:
    op = partial(
        core.watermark,
        text=args.text,
        position=args.position,
        opacity=args.opacity,
        font_size=args.font_size,
    )
    return _dispatch(args, op, {})


def cmd_montage(args) -> int:
    # Many-to-one: gather all inputs and emit a single contact-sheet image.
    recursive = getattr(args, "recursive", False)
    inputs = collect_inputs(args.input, recursive=recursive)
    if not inputs:
        _err(f"no matching input images for {args.input!r}")
        return 2
    out = Path(args.out) if args.out else Path("montage.png")
    try:
        result = core.montage(
            inputs,
            out,
            columns=args.columns,
            cell=args.cell,
            padding=args.padding,
            background=args.background,
        )
    except ImageToolkitError as exc:
        _err(str(exc))
        return 1
    print(f"wrote {result}")
    return 0


def cmd_info(args) -> int:
    recursive = getattr(args, "recursive", False)
    inputs = collect_inputs(args.input, recursive=recursive)
    if not inputs:
        _err(f"no matching input images for {args.input!r}")
        return 2
    rc = 0
    for in_path in inputs:
        try:
            print(core.info(in_path))
        except ImageToolkitError as exc:
            _err(f"{in_path}: {exc}")
            rc = 1
    return rc


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def _add_io_args(
    p: argparse.ArgumentParser,
    *,
    out: bool = True,
    outdir: bool = True,
    recursive: bool = True,
) -> None:
    if out:
        p.add_argument("-o", "--out", help="output file (single input only)")
    if outdir:
        p.add_argument("--outdir", help="output directory (for batches)")
    if recursive:
        p.add_argument(
            "-r",
            "--recursive",
            action="store_true",
            help="recurse into subdirectories when INPUT is a directory",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image-toolkit",
        description="Batch image processing: convert, resize, strip metadata, "
        "rotate/flip, thumbnail, grayscale, watermark, montage, info.",
    )
    parser.add_argument(
        "--version", action="version", version=f"image-toolkit {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # convert
    p = sub.add_parser("convert", help="convert image(s) to another format")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "--to", required=True, help="target format: png|jpg|jpeg|webp|gif|bmp|tiff|..."
    )
    _add_io_args(p)
    p.set_defaults(func=cmd_convert)

    # resize
    p = sub.add_parser("resize", help="resize image(s)")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "--max", type=int, help="scale so the longest side == MAX (never upscales)"
    )
    p.add_argument("--width", type=int, help="target width")
    p.add_argument("--height", type=int, help="target height")
    p.add_argument("--percent", type=float, help="scale by this percentage")
    _add_io_args(p)
    p.set_defaults(func=cmd_resize)

    # strip-exif
    p = sub.add_parser("strip-exif", help="remove all metadata")
    p.add_argument("input", help="image file, directory, or glob")
    _add_io_args(p)
    p.set_defaults(func=cmd_strip_exif)

    # rotate
    p = sub.add_parser("rotate", help="rotate image(s) counter-clockwise")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "--degrees",
        type=float,
        required=True,
        help="rotation in degrees (counter-clockwise)",
    )
    p.add_argument(
        "--no-expand",
        action="store_true",
        help="keep original canvas size (may clip corners)",
    )
    _add_io_args(p)
    p.set_defaults(func=cmd_rotate)

    # flip
    p = sub.add_parser("flip", help="mirror image(s)")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument("--horizontal", action="store_true", help="mirror left/right")
    p.add_argument("--vertical", action="store_true", help="mirror top/bottom")
    _add_io_args(p)
    p.set_defaults(func=cmd_flip)

    # thumbnail
    p = sub.add_parser("thumbnail", help="make thumbnail(s)")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "--size", type=int, default=200, help="max longest side in px (default 200)"
    )
    _add_io_args(p)
    p.set_defaults(func=cmd_thumbnail)

    # grayscale
    p = sub.add_parser("grayscale", help="convert to grayscale")
    p.add_argument("input", help="image file, directory, or glob")
    _add_io_args(p)
    p.set_defaults(func=cmd_grayscale)

    # watermark
    p = sub.add_parser("watermark", help="add a text watermark")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument("--text", required=True, help="watermark text")
    p.add_argument(
        "--position",
        default="bottom-right",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        help="placement (default bottom-right)",
    )
    p.add_argument("--opacity", type=float, default=0.5, help="0..1 (default 0.5)")
    p.add_argument(
        "--font-size",
        type=int,
        default=None,
        help="font size in px (default: scaled to image)",
    )
    _add_io_args(p)
    p.set_defaults(func=cmd_watermark)

    # montage
    p = sub.add_parser(
        "montage", help="tile many images into a single contact-sheet grid"
    )
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "--columns",
        type=int,
        default=None,
        help="grid columns (default: near-square; an explicit value is used "
        "as-is, even if it exceeds the image count)",
    )
    p.add_argument(
        "--cell", type=int, default=200, help="max thumbnail box in px (default 200)"
    )
    p.add_argument(
        "--padding", type=int, default=8, help="gap between cells in px (default 8)"
    )
    p.add_argument(
        "--background",
        default="#ffffff",
        help="sheet background: name or #RRGGBB (default white)",
    )
    p.add_argument(
        "-o",
        "--out",
        help="output image file (default montage.png; an existing file at this "
        "path is silently overwritten)",
    )
    p.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="recurse into subdirectories when INPUT is a directory",
    )
    p.set_defaults(func=cmd_montage)

    # info
    p = sub.add_parser("info", help="print format/size/mode/has-exif")
    p.add_argument("input", help="image file, directory, or glob")
    p.add_argument(
        "-r", "--recursive", action="store_true", help="recurse into subdirectories"
    )
    p.set_defaults(func=cmd_info)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ImageToolkitError as exc:
        _err(str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        _err("interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
