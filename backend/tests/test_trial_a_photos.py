"""Trial A: photos are shrunk on upload, upright and without EXIF / GPS (D-282)."""

from __future__ import annotations

import base64
import io
import uuid
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hse_enums import AttachmentOwner
from app.models import Attachment, Project, User
from app.services import attachments, images
from app.services.field import common as fc
from tests.conftest import Api, Ids
from tests.hse_helpers import API, create_incident

GPS_IFD = 0x8825


def photo(
    w: int = 4032,
    h: int = 3024,
    orientation: int = 6,
    gps: bool = True,
    fmt: str = "JPEG",
    mode: str = "RGB",
) -> bytes:
    """A noisy phone-like photo (hard to compress) with orientation, maker and GPS tags."""
    base = Image.effect_noise((max(1, w // 8), max(1, h // 8)), 40).resize((w, h))
    im = Image.merge("RGB", (base, base.rotate(90, expand=False), base)).convert(mode)
    ex = Image.Exif()
    ex[0x0112] = orientation
    ex[0x010F] = "PhoneMaker"
    ex[0x013B] = "Site Engineer"  # artist: personal
    if gps:
        g = ex.get_ifd(GPS_IFD)
        g[1], g[2], g[3], g[4] = "N", (24.0, 57.0, 4.5), "E", (46.0, 42.0, 1.2)
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.save(buf, "JPEG", quality=95, exif=ex.tobytes())
    else:
        im.save(buf, "PNG", exif=ex.tobytes())
    return buf.getvalue()


def opened(b: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(b))
    im.load()
    return im


def no_metadata(b: bytes) -> bool:
    im = opened(b)
    return not dict(im.getexif()) and "exif" not in im.info and b"PhoneMaker" not in b


# ---- the shrinker --------------------------------------------------------------------------------


def test_phone_photo_is_shrunk_upright_and_clean() -> None:
    raw = photo()
    assert len(raw) > 3 * 1024 * 1024
    r = images.shrink(raw, "image/jpeg", "IMG_0042.JPG")
    assert r.changed and r.content_type == "image/jpeg" and r.file_name == "IMG_0042.JPG"
    im = opened(r.content)
    assert im.format == "JPEG"
    assert im.size == (1200, 1600)  # orientation 6 applied: portrait, long edge 1600
    assert len(r.content) <= 640 * 1024  # about 0.5 MB even for a noisy photo
    assert no_metadata(r.content)


def test_document_profile_keeps_a_larger_long_edge() -> None:
    r = images.shrink(photo(orientation=1), "image/jpeg", "iqama.jpg", images.DOCUMENT)
    assert opened(r.content).size == (2400, 1800)
    assert len(r.content) <= 1300 * 1024
    assert no_metadata(r.content)


def test_png_photo_without_transparency_becomes_jpeg() -> None:
    raw = photo(2000, 1500, orientation=1, gps=False, fmt="PNG")
    r = images.shrink(raw, "image/png", "scene.png")
    assert r.content_type == "image/jpeg" and r.file_name == "scene.jpg"
    assert opened(r.content).size == (1600, 1200)


def test_transparent_png_stays_png() -> None:
    im = Image.new("RGBA", (3000, 1000), (0, 0, 0, 0))
    im.paste((10, 10, 10, 255), (100, 100, 2900, 900))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    r = images.shrink(buf.getvalue(), "image/png", "mark.png")
    out = opened(r.content)
    assert r.content_type == "image/png" and out.format == "PNG" and out.mode == "RGBA"
    assert out.size == (1600, 533)


def test_small_photo_is_not_made_bigger_but_loses_its_metadata() -> None:
    raw = photo(800, 600, orientation=1)
    r = images.shrink(raw, "image/jpeg", "small.jpg")
    assert len(r.content) <= len(raw)
    assert opened(r.content).size == (800, 600)
    assert no_metadata(r.content)


def test_other_files_and_unreadable_images_are_untouched() -> None:
    pdf = b"%PDF-1.4\n" + b"0" * 4096
    assert images.shrink(pdf, "application/pdf", "report.pdf").content == pdf
    junk = b"\xff\xd8\xff" + b"0" * 100
    r = images.shrink(junk, "image/jpeg", "broken.jpg")
    assert r.content == junk and not r.changed


# ---- every upload path ---------------------------------------------------------------------------


def test_generic_upload_shrinks_incident_photo(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    inc = create_incident(n, ids)
    raw = photo()
    res = n.post(
        f"{API}/attachments",
        data={"owner_type": "incident", "owner_id": inc["id"]},
        files={"file": ("IMG_0042.jpg", raw, "image/jpeg")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["size_bytes"] < len(raw) // 5 and body["content_type"] == "image/jpeg"
    a = db.get(Attachment, uuid.UUID(body["id"]))
    assert a is not None
    stored = attachments.read_content(a)
    assert len(stored) == a.size_bytes and no_metadata(stored)
    assert opened(stored).size == (1200, 1600)


def _project_user(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    pid = db.scalars(select(Project.id).where(Project.code == "ANIA-EXP")).one()
    uid = db.scalars(select(User.id).where(User.email == "noura.qahtani@example.com")).one()
    return pid, uid


def test_inline_field_photos_are_shrunk(db: Session) -> None:
    pid, uid = _project_user(db)
    raw = photo()
    p = SimpleNamespace(file_name="edge.jpg", content_base64=base64.b64encode(raw).decode())
    (aid,) = fc.store_photos(db, AttachmentOwner.field_photo, uuid.uuid4(), pid, [p], uid, "x")
    a = db.get(Attachment, aid)
    assert a is not None and a.size_bytes < len(raw) // 5
    assert no_metadata(attachments.read_content(a))


def test_personal_bucket_photo_is_shrunk_before_encryption(db: Session) -> None:
    pid, uid = _project_user(db)
    raw = photo()
    a = attachments.store(
        db, AttachmentOwner.worker_id_copy, uuid.uuid4(), pid, "iqama.jpg", raw, "image/jpeg", uid
    )
    assert a.storage_bucket == "personal"
    stored = attachments.read_content(a)
    assert opened(stored).size == (1800, 2400)  # document profile
    assert no_metadata(stored)


def test_report_files_signatures_and_imports_keep_their_bytes(db: Session) -> None:
    pid, uid = _project_user(db)
    raw = photo(2400, 1800)
    for owner in (AttachmentOwner.incident_accident_report, AttachmentOwner.toolbox_signature):
        a = attachments.store(db, owner, uuid.uuid4(), pid, "x.jpg", raw, "image/jpeg", uid)
        assert attachments.read_content(a) == raw, owner
    a = attachments.store(
        db,
        AttachmentOwner.personnel_cert_scan,
        uuid.uuid4(),
        pid,
        "scan.jpg",
        raw,
        "image/jpeg",
        uid,
        shrink=False,
    )
    assert attachments.read_content(a) == raw
