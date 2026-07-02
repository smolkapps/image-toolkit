"""image-toolkit: batch image processing CLI built on Pillow.

Public API re-exports the core operations so callers can do::

    from image_toolkit import convert, resize, strip_exif

All operations work on a single file. Batch orchestration over a
directory / glob lives in :mod:`image_toolkit.batch`.
"""

from .core import (
    ImageToolkitError,
    UnsupportedFormatError,
    InputNotFoundError,
    convert,
    resize,
    strip_exif,
    rotate,
    flip,
    thumbnail,
    grayscale,
    watermark,
    montage,
    info,
    ImageInfo,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ImageToolkitError",
    "UnsupportedFormatError",
    "InputNotFoundError",
    "convert",
    "resize",
    "strip_exif",
    "rotate",
    "flip",
    "thumbnail",
    "grayscale",
    "watermark",
    "montage",
    "info",
    "ImageInfo",
]
