"""Isolations / LOTO register, locks, personal lock events, lock cuts and long-term reviews
(spec 3-ptw §3.11, §4.4, §4.5, §5.5)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.ptw_enums import (
    EnergyType,
    IsolationMethod,
    IsolationStatus,
    LockStatus,
    LockType,
    PersonalLockRemoval,
    VerificationMethod,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import UserRef
from app.schemas.ptw_common import PermitRef

# ---- locks --------------------------------------------------------------------------------------


class LockCreate(StrictInput):
    """Register a lock (isolation lock / lockbox: capability 92; personal lock: 93). lock_no is
    assigned `L-<short>-nnnn` / `P-…` / `LB-…` unless given (unique per project)."""

    lock_type: LockType
    lock_no: str | None = Field(default=None, max_length=20, examples=["P-ANIA-1104"])
    holder_worker_id: uuid.UUID | None = Field(
        default=None, description="Personal locks: one holder, one key."
    )


class LockUpdate(PatchInput):
    holder_worker_id: uuid.UUID | None = None


class LockLostInput(StrictInput):
    """IS-11: lost → linked permits Suspended `isolation_breach` until the point is re-locked."""

    detail: str = Field(min_length=10, max_length=300)


class LockRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    lock_no: str
    lock_type: LockType
    holder_worker: WorkerRef | None
    status: LockStatus
    applied_on: str | None = Field(examples=["ISO-ANIA-EXP-2026-0061 point 1", "LB-ANIA-012"])
    updated_at: datetime


LockPage = Page[LockRead]


# ---- isolation certificates ---------------------------------------------------------------------


class IsolationPointInput(StrictInput):
    energy_type: EnergyType
    device_tag: str = Field(min_length=1, max_length=40, examples=["Q12"])
    location: str = Field(min_length=1, max_length=200)
    method: IsolationMethod


class IsolationPointUpdate(PatchInput):
    non_nullable = frozenset({"energy_type", "device_tag", "location", "method"})

    energy_type: EnergyType | None = None
    device_tag: str | None = Field(default=None, min_length=1, max_length=40)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    method: IsolationMethod | None = None


class PointApplyInput(StrictInput):
    """IS-2/IS-3: one isolation lock and one danger/hold tag per point (LOCK_NOT_AVAILABLE)."""

    isolation_lock_id: uuid.UUID
    tag_no: str = Field(min_length=1, max_length=20, examples=["DT-0231"])
    applied_at: datetime


class PointVerifyInput(StrictInput):
    """IS-4: verifier ≠ applier (VERIFIER_IS_APPLIER, AC38), method suited to the energy."""

    verified_by_user_id: uuid.UUID | None = Field(default=None, description="Default: caller.")
    verified_by_worker_id: uuid.UUID | None = None
    verified_at: datetime
    verification_method: VerificationMethod


class PointRemoveInput(StrictInput):
    removed_at: datetime


class IsolationPointRead(ApiModel):
    id: uuid.UUID
    point_no: int
    energy_type: EnergyType
    device_tag: str
    location: str
    method: IsolationMethod
    isolation_lock_no: str | None
    tag_no: str | None
    applied_by: UserRef | None
    applied_at: datetime | None
    verified_by_user: UserRef | None
    verified_by_worker: WorkerRef | None
    verified_at: datetime | None
    verification_method: VerificationMethod | None
    removed_by: UserRef | None
    removed_at: datetime | None


class IsolationCreate(StrictInput):
    """Capability 92 + isolation_authority appointment with the matching discipline
    (electrical_hv for HV, APPOINTMENT_INVALID, AC42) → planned. HV: earths applied as points
    with method earth_applied and a switching programme (IS-10)."""

    equipment_desc: str = Field(min_length=1, max_length=200)
    energy_types: list[EnergyType] = Field(min_length=1)
    hv: bool = False
    isolation_authority_user_id: uuid.UUID
    lockbox_id: uuid.UUID
    points: list[IsolationPointInput] = Field(min_length=1)
    switching_programme_ref: str | None = Field(default=None, max_length=40)


class IsolationUpdate(PatchInput):
    """Planned only."""

    non_nullable = frozenset({"equipment_desc", "energy_types", "lockbox_id"})

    equipment_desc: str | None = Field(default=None, min_length=1, max_length=200)
    energy_types: list[EnergyType] | None = Field(default=None, min_length=1)
    lockbox_id: uuid.UUID | None = None
    switching_programme_ref: str | None = Field(default=None, max_length=40)


class IsolationTransition(StrictInput):
    """§4.4: planned → isolated (every point applied with lock + tag); isolated → verified
    (every point verified); verified → deisolation_requested (IS-7: linked permits ended and
    post-expiry checks done, no personal lock on the lockbox, else DEISOLATION_BLOCKED with
    meta.permits / meta.locks); deisolation_requested → deisolated (authorised by an issuer,
    capability 94, and every point removed); planned → cancelled."""

    to_status: IsolationStatus
    comment: str | None = Field(default=None, max_length=500)


class LongTermReviewInput(StrictInput):
    """IS-8 weekly review by the isolation authority. lock_tag_in_place = false →
    `isolation_breach` on every linked live permit (AC43)."""

    lock_tag_in_place: bool
    note: str | None = Field(default=None, max_length=500)


class LongTermReviewRead(ApiModel):
    reviewed_by: UserRef
    reviewed_at: datetime
    lock_tag_in_place: bool
    note: str | None


class PersonalLockApply(StrictInput):
    """IS-5 group lockout (capability 93): each crew member working on the isolated equipment
    applies their own personal lock on the certificate's lockbox before the shift starts."""

    lock_id: uuid.UUID
    worker_id: uuid.UUID
    applied_at: datetime
    permit_id: uuid.UUID | None = None


class PersonalLockRemove(StrictInput):
    """The holder removes their own lock (capability 93)."""

    removed_at: datetime


class LockCutInput(StrictInput):
    """IS-9 (OSHA 1910.147(e)(3)): HSE Manager only (capability 95, else 403, AC41). Audited and
    alerted to the HSE Manager, HSE Officers and the holder's Contractor HSE Rep."""

    supervisor_worker_id: uuid.UUID | None = None
    supervisor_user_id: uuid.UUID | None = None
    supervisor_confirmed_absent_at: datetime
    contact_attempts: str = Field(min_length=10, max_length=500)
    worker_informed_at: datetime | None = Field(
        default=None, description="Before the holder returns to work; may be recorded later."
    )


class WorkerInformedInput(StrictInput):
    worker_informed_at: datetime


class LockCutRead(ApiModel):
    approved_by: UserRef
    supervisor_confirmed_absent_at: datetime
    contact_attempts: str
    worker_informed_at: datetime | None
    cut_at: datetime


class PersonalLockEventRead(ApiModel):
    id: uuid.UUID
    lock_no: str
    lockbox_no: str
    worker: WorkerRef | None = Field(description="Null without capability 46.")
    permit: PermitRef | None
    applied_at: datetime
    removed_at: datetime | None
    removed_by: PersonalLockRemoval | None
    cut: LockCutRead | None


class PersonalLockList(ApiModel):
    items: list[PersonalLockEventRead]


class IsolationRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    iso_no: str = Field(examples=["ISO-ANIA-EXP-2026-0061"])
    equipment_desc: str
    energy_types: list[EnergyType]
    hv: bool
    isolation_authority: UserRef
    lockbox_no: str
    lockbox_id: uuid.UUID
    switching_programme_ref: str | None
    points: list[IsolationPointRead]
    personal_locks_applied: list[PersonalLockEventRead]
    permits: list[PermitRef] = Field(description="Permits linked to it (IS-6).")
    long_term: bool = Field(description="Verified longer than long_term_isolation_days.")
    verified_since: datetime | None
    last_review: LongTermReviewRead | None
    review_due_at: datetime | None
    deisolation_authorised_by: UserRef | None
    deisolation_authorised_at: datetime | None
    deisolation_blockers: list[str] = Field(
        description="Why de-isolation cannot be requested now (permit numbers, lock numbers)."
    )
    status: IsolationStatus
    created_at: datetime
    updated_at: datetime


IsolationPage = Page[IsolationRead]
