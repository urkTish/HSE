"""Photo shrinking on upload (D-282) and metadata stripping (EXE-5, P6d-3, D-176).

Phone photos arrive at 3-12 MB; stored as they are they fill the trial's 10 GB quickly and are
slow to open on site networks. `shrink` re-encodes JPEG / PNG images:

- EXIF orientation is applied to the pixels (the photo stays upright without the tag);
- the long edge is reduced to 1600 px (2400 px for scans of documents, so small print stays
  readable) and the image saved as JPEG quality 80 (85 for documents); when the result is still
  over about 0.5 MB (1 MB for documents) the quality steps down to 60 at the lowest;
- nothing of the original metadata is written back: EXIF (GPS position, device, owner, dates),
  XMP, IPTC, comments and PNG text chunks are all dropped (the colour profile is kept);
- images with real transparency (signatures, marked-up screenshots) stay PNG, only resized;
- a small image that needs no resize or rotation keeps its own encoding when that is smaller
  (metadata stripped), so re-encoding never makes a file bigger;
- anything Pillow cannot read (or an image bomb) is returned unchanged: type checks happen
  earlier, and refusing here would break uploads that worked before.

PDFs and other files are never touched.
"""

from __future__ import annotations

import io
import logging
import struct
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger("hse.images")

IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})
ORIENTATION_TAG = 0x0112


@dataclass(frozen=True)
class Profile:
    long_edge: int
    quality: int
    target_bytes: int
    min_quality: int = 60


PHOTO = Profile(long_edge=1600, quality=80, target_bytes=512 * 1024)
DOCUMENT = Profile(long_edge=2400, quality=85, target_bytes=1024 * 1024)


@dataclass(frozen=True)
class Result:
    content: bytes
    content_type: str
    file_name: str
    changed: bool


# ---- metadata stripping without decoding (also used for inline field photos) -------------------


def _strip_jpeg(b: bytes) -> bytes:
    """Drop APP1…APP15 (EXIF, XMP, GPS, maker data) and COM segments; keep APP0 and image data."""
    if not b.startswith(b"\xff\xd8"):
        return b
    out = bytearray(b[:2])
    i = 2
    while i + 4 <= len(b):
        if b[i] != 0xFF:
            break
        marker = b[i + 1]
        if marker == 0xDA:  # start of scan: the rest is image data
            out += b[i:]
            return bytes(out)
        (length,) = struct.unpack(">H", b[i + 2 : i + 4])
        seg = b[i : i + 2 + length]
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
            out += seg
        i += 2 + length
    out += b[i:]
    return bytes(out)


def _strip_png(b: bytes) -> bytes:
    """Drop eXIf and text chunks (tEXt, zTXt, iTXt) and the time chunk."""
    sig = b"\x89PNG\r\n\x1a\n"
    if not b.startswith(sig):
        return b
    out = bytearray(sig)
    i = len(sig)
    while i + 8 <= len(b):
        (n,) = struct.unpack(">I", b[i : i + 4])
        kind = b[i + 4 : i + 8]
        chunk = b[i : i + 12 + n]
        if kind not in (b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"):
            out += chunk
        i += 12 + n
    return bytes(out)


def strip_metadata(b: bytes) -> bytes:
    return _strip_png(_strip_jpeg(b))


# ---- shrinking -----------------------------------------------------------------------------------


def _has_alpha(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA") if im.mode not in ("RGBA", "LA") else im
        extrema = rgba.getchannel("A").getextrema()
        return int(extrema[0]) < 255  # type: ignore[arg-type]
    return False


def _jpeg(im: Image.Image, p: Profile, icc: bytes | None) -> bytes:
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    extra = {"icc_profile": icc} if icc else {}
    q = p.quality
    while True:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True, **extra)
        if buf.tell() <= p.target_bytes or q <= p.min_quality:
            return buf.getvalue()
        q = max(p.min_quality, q - 5)


def _png(im: Image.Image, icc: bytes | None) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True, **({"icc_profile": icc} if icc else {}))
    return buf.getvalue()


def _renamed(file_name: str, ext: str) -> str:
    stem = Path(file_name).stem or "photo"
    return f"{stem}{ext}"


def shrink(content: bytes, content_type: str, file_name: str, profile: Profile = PHOTO) -> Result:
    if content_type not in IMAGE_TYPES:
        return Result(content, content_type, file_name, False)
    try:
        with warnings.catch_warnings(), Image.open(io.BytesIO(content)) as src:
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            w, h = src.size
            scale = min(1.0, profile.long_edge / max(w, h))
            box = (max(1, round(w * scale)), max(1, round(h * scale)))
            if src.format == "JPEG":
                src.draft("RGB", box)  # decode at 1/2, 1/4 or 1/8 when that is still big enough
            if src.mode in ("I", "F") or src.mode.startswith("I;"):  # 16-bit / float scans
                raise ValueError(f"mode {src.mode} is kept as uploaded")
            src.load()
            icc = src.info.get("icc_profile")  # colour profile: not personal, keeps colours true
            orientation = src.getexif().get(ORIENTATION_TAG, 1)
            im = ImageOps.exif_transpose(src)
            resized = max(im.size) > profile.long_edge
            if resized:
                im.thumbnail((profile.long_edge, profile.long_edge), Image.Resampling.LANCZOS)
            if _has_alpha(im):
                out, ctype, ext = _png(im, icc), "image/png", ".png"
            else:
                out, ctype, ext = _jpeg(im, profile, icc), "image/jpeg", ".jpg"
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Warning) as e:
        log.info("photo not re-encoded (%s): %s", type(e).__name__, file_name)
        return Result(content, content_type, file_name, False)
    if not resized and orientation in (1, None):
        stripped = strip_metadata(content)
        if len(stripped) <= len(out):
            return Result(stripped, content_type, file_name, stripped != content)
    name = file_name if ctype == content_type else _renamed(file_name, ext)
    return Result(out, ctype, name, True)
