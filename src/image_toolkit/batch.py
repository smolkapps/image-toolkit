"""Batch orchestration: apply a single-file operation across many inputs.

The CLI resolves an INPUT argument into a list of files via
:func:`collect_inputs` (handling a single file, a directory, or a glob), then
calls :func:`run_batch` to apply an operation to each, routing outputs into an
``outdir`` (mirroring the source tree when ``recursive`` is used).
"""

from __future__ import annotations

import glob as _glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .core import ImageToolkitError

# Extensions we treat as images when scanning a directory.
IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".ico",
    ".ppm",
    ".tga",
}


def _looks_like_glob(s: str) -> bool:
    return any(ch in s for ch in "*?[")


def collect_inputs(inp: str, *, recursive: bool = False) -> List[Path]:
    """Resolve INPUT into a sorted list of image file paths.

    * a single existing file -> just that file (regardless of extension),
    * a directory -> image files inside it (recursively if ``recursive``),
    * a glob pattern -> matching files filtered to known image extensions.
    """
    p = Path(inp)

    if p.is_file():
        return [p]

    if p.is_dir():
        if recursive:
            it = (
                Path(root) / name for root, _dirs, files in os.walk(p) for name in files
            )
        else:
            it = (c for c in p.iterdir() if c.is_file())
        found = [c for c in it if c.suffix.lower() in IMAGE_EXTS]
        return sorted(found)

    if _looks_like_glob(inp):
        matches = [Path(m) for m in _glob.glob(inp, recursive=recursive)]
        found = [m for m in matches if m.is_file() and m.suffix.lower() in IMAGE_EXTS]
        return sorted(found)

    # Nothing matched.
    return []


@dataclass
class BatchResult:
    inputs: List[Path] = field(default_factory=list)
    outputs: List[Path] = field(default_factory=list)
    failures: List[tuple] = field(default_factory=list)  # (path, error_msg)

    @property
    def ok(self) -> int:
        return len(self.outputs)

    @property
    def failed(self) -> int:
        return len(self.failures)


def _out_path_for(
    in_path: Path, *, base: Optional[Path], outdir: Optional[Path], recursive: bool
) -> Optional[Path]:
    """Compute the output directory to hand the op for a given input.

    When ``recursive`` and a ``base`` directory is known, mirror the relative
    subtree under ``outdir`` so nested files don't collide.
    """
    if outdir is None:
        return None
    if recursive and base is not None:
        try:
            rel_parent = in_path.parent.relative_to(base)
        except ValueError:
            rel_parent = Path(".")
        target = outdir / rel_parent
    else:
        target = outdir
    return target


def run_batch(
    inputs: Sequence[Path],
    op: Callable[..., Path],
    *,
    base: Optional[Path] = None,
    outdir: Optional[Path] = None,
    recursive: bool = False,
    op_kwargs: Optional[dict] = None,
    single_out: Optional[Path] = None,
) -> BatchResult:
    """Apply ``op(in_path, ..., outdir=<dir>)`` to each input.

    ``op`` must accept a positional input path and an ``outdir`` keyword. For
    the single-file case the caller may pass ``single_out`` to honor an explicit
    ``-o/--out`` path (only valid when there is exactly one input).
    """
    op_kwargs = dict(op_kwargs or {})
    result = BatchResult(inputs=list(inputs))

    if single_out is not None and len(inputs) == 1:
        in_path = Path(inputs[0])
        try:
            out = op(in_path, out=single_out, **op_kwargs)
            result.outputs.append(Path(out))
        except ImageToolkitError as exc:
            result.failures.append((in_path, str(exc)))
        return result

    for in_path in inputs:
        in_path = Path(in_path)
        target_dir = _out_path_for(
            in_path, base=base, outdir=outdir, recursive=recursive
        )
        try:
            out = op(in_path, outdir=target_dir, **op_kwargs)
            result.outputs.append(Path(out))
        except ImageToolkitError as exc:
            result.failures.append((in_path, str(exc)))
    return result
