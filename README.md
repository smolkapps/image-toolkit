# image-toolkit

A small, fast, **offline** command-line toolkit for batch image processing,
built on [Pillow](https://python-pillow.org/). No network, no API keys, no
telemetry — it reads and writes local image files and nothing else.

Operates on a single file, an entire directory, or a glob pattern.

## Install

```bash
pip install -e .
# with tests:
pip install -e ".[test]"
```

This installs two equivalent console scripts: `image-toolkit` and the short
alias `imgtk`.

Runtime dependency: **Pillow** only.

## Usage

```text
image-toolkit <command> INPUT [options]
```

`INPUT` may be a file, a directory, or a glob (e.g. `'./photos/*.jpg'`). For a
single input use `-o/--out`; for batches use `--outdir` (add `-r/--recursive`
to walk subdirectories, mirroring the tree under the output dir).

### Commands

| Command | What it does |
|---|---|
| `convert IN --to png\|jpg\|webp\|... -o OUT` | Change format (preserves EXIF) |
| `resize IN --max 1024` | Scale so the longest side is 1024px (never upscales) |
| `resize IN --width W --height H` | Explicit size; pass just one to keep aspect |
| `resize IN --percent 50` | Scale by percentage |
| `strip-exif IN -o OUT` | Remove all metadata |
| `rotate IN --degrees 90` | Rotate counter-clockwise (canvas expands) |
| `flip IN --horizontal\|--vertical` | Mirror |
| `thumbnail IN --size 200 --outdir thumbs/` | Thumbnail, longest side ≤ size |
| `grayscale IN -o OUT` | Convert to grayscale (mode `L`) |
| `watermark IN --text "© 2026" --position bottom-right --opacity 0.5 -o OUT` | Text watermark |
| `montage IN --columns 4 --cell 200 -o sheet.png` | Tile many images into one contact sheet |
| `info IN` | Print format, size, mode, has-exif |

### Examples

```bash
# Convert a single PNG to WebP
image-toolkit convert logo.png --to webp -o logo.webp

# Resize every JPG in ./photos so the long edge is 1600px, into ./resized
image-toolkit resize ./photos --max 1600 --outdir ./resized

# Recurse and resize an entire tree
image-toolkit resize ./photos --max 1600 --outdir ./resized --recursive

# Strip metadata before sharing
image-toolkit strip-exif vacation.jpg -o vacation_clean.jpg

# Make 200px thumbnails for a folder
image-toolkit thumbnail ./photos --size 200 --outdir ./thumbs

# Watermark, semi-transparent, bottom-right
image-toolkit watermark photo.jpg --text "© 2026 me" --opacity 0.4 -o out.jpg

# Build a contact sheet from a folder (auto near-square grid)
image-toolkit montage ./photos --cell 240 -o contact-sheet.png

# Inspect
image-toolkit info photo.jpg
```

## Behavior notes

- **Never upscales on `--max` / `thumbnail`** — if the image is already smaller
  than the target, dimensions are left unchanged.
- **Aspect ratio is preserved by default.** Supplying both `--width` and
  `--height` forces an exact (possibly non-proportional) size.
- **Alpha-incompatible targets** (JPEG/BMP/PPM) are flattened onto a white
  background automatically.
- **EXIF** is carried through `convert`/`resize`/`rotate`/`flip`/`grayscale` by
  default and dropped by `strip-exif`/`thumbnail`.
- **Exit codes**: `0` success, `1` an operation failed, `2` bad usage / no
  matching inputs. Errors go to stderr.

## Development

All builds and tests for this project are run on a Linux host; locally you can:

```bash
python -m pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
