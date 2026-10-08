"""Isolations / LOTO: certificates, points, locks, personal locks, lock cuts and long-term
reviews (spec 3-ptw §3.11, §4.4, §4.5, §5.5)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.ptw_enums import EnergyType, IsolationStatus, LockStatus, LockType
from app.schemas.isolations import (
    IsolationCreate,
    IsolationPage,
    IsolationPointInput,
    IsolationPointUpdate,
    IsolationRead,
    IsolationTransition,
    IsolationUpdate,
    LockCreate,
    LockCutInput,
    LockLostInput,
    LockPage,
    LockRead,
    LockUpdate,
    LongTermReviewInput,
    PersonalLockApply,
    PersonalLockEventRead,
    PersonalLockList,
    PersonalLockRemove,
    PointApplyInput,
    PointRemoveInput,
    PointVerifyInput,
    WorkerInformedInput,
)
from app.services.ptw import isolations as svc

router = APIRouter(tags=["isolations"])


@router.get(
    "/projects/{project_id}/isolations",
    response_model=IsolationPage,
    summary="Isolation register (long-term flags, review due)",
    responses=error_responses(401, 403, 404, 422),
)
def list_isolations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[IsolationStatus] | None, Query(alias="status")] = None,
    energy_type: Annotated[list[EnergyType] | None, Query()] = None,
    permit_id: uuid.UUID | None = None,
    long_term: bool | None = None,
    review_due: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> IsolationPage:
    return svc.list_certs(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        energy_type,
        permit_id,
        long_term,
        review_due,
        q,
    )


@router.post(
    "/projects/{project_id}/isolations",
    response_model=IsolationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan an isolation certificate (capability 92; isolation authority appointment)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_isolation(
    project_id: uuid.UUID,
    body: IsolationCreate,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/isolations/{isolation_id}",
    response_model=IsolationRead,
    summary="Get an isolation certificate",
    responses=error_responses(401, 403, 404),
)
def get_isolation(isolation_id: uuid.UUID, user: CurrentUser, db: DB) -> IsolationRead:
    return svc.read(db, user, isolation_id)


@router.patch(
    "/isolations/{isolation_id}",
    response_model=IsolationRead,
    summary="Edit a planned isolation",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_isolation(
    isolation_id: uuid.UUID,
    body: IsolationUpdate,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.update(db, user, isolation_id, body)


@router.post(
    "/isolations/{isolation_id}/points",
    response_model=IsolationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an isolation point (planned only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_isolation_point(
    isolation_id: uuid.UUID,
    body: IsolationPointInput,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.add_point(db, user, isolation_id, body)


@router.patch(
    "/isolations/{isolation_id}/points/{point_id}",
    response_model=IsolationRead,
    summary="Edit an isolation point (planned only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_isolation_point(
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    body: IsolationPointUpdate,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.update_point(db, user, isolation_id, point_id, body)


@router.delete(
    "/isolations/{isolation_id}/points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an isolation point (planned only)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_isolation_point(
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> None:
    svc.delete_point(db, user, isolation_id, point_id)


@router.post(
    "/isolations/{isolation_id}/points/{point_id}/apply",
    response_model=IsolationRead,
    summary="Apply lock and tag to a point (IS-2/IS-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def apply_isolation_point(
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    body: PointApplyInput,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.apply_point(db, user, isolation_id, point_id, body)


@router.post(
    "/isolations/{isolation_id}/points/{point_id}/verify",
    response_model=IsolationRead,
    summary="Verify a point (verifier ≠ applier, VERIFIER_IS_APPLIER)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def verify_isolation_point(
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    body: PointVerifyInput,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.verify_point(db, user, isolation_id, point_id, body)


@router.post(
    "/isolations/{isolation_id}/points/{point_id}/remove",
    response_model=IsolationRead,
    summary="Remove lock and tag (de-isolation)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def remove_isolation_point(
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    body: PointRemoveInput,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.remove_point(db, user, isolation_id, point_id, body)


@router.post(
    "/isolations/{isolation_id}/transitions",
    response_model=IsolationRead,
    summary="Isolation lifecycle (§4.4; DEISOLATION_BLOCKED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_isolation(
    isolation_id: uuid.UUID,
    body: IsolationTransition,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.transition(db, user, isolation_id, body)


@router.post(
    "/isolations/{isolation_id}/reviews",
    response_model=IsolationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Weekly long-term isolation review (IS-8)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_long_term_isolation(
    isolation_id: uuid.UUID,
    body: LongTermReviewInput,
    user: CurrentUser,
    db: DB,
) -> IsolationRead:
    return svc.review(db, user, isolation_id, body)


@router.get(
    "/isolations/{isolation_id}/personal-locks",
    response_model=PersonalLockList,
    summary="Personal lock events on the certificate's lockbox",
    responses=error_responses(401, 403, 404),
)
def list_personal_locks(isolation_id: uuid.UUID, user: CurrentUser, db: DB) -> PersonalLockList:
    return svc.list_personal(db, user, isolation_id)


@router.post(
    "/isolations/{isolation_id}/personal-locks",
    response_model=PersonalLockEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply a personal lock (IS-5; capability 93)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def apply_personal_lock(
    isolation_id: uuid.UUID,
    body: PersonalLockApply,
    user: CurrentUser,
    db: DB,
) -> PersonalLockEventRead:
    return svc.apply_personal(db, user, isolation_id, body)


@router.post(
    "/personal-lock-events/{event_id}/remove",
    response_model=PersonalLockEventRead,
    summary="The holder removes their personal lock",
    responses=error_responses(401, 403, 404, 409, 422),
)
def remove_personal_lock(
    event_id: uuid.UUID,
    body: PersonalLockRemove,
    user: CurrentUser,
    db: DB,
) -> PersonalLockEventRead:
    return svc.remove_personal(db, user, event_id, body)


@router.post(
    "/personal-lock-events/{event_id}/cut",
    response_model=PersonalLockEventRead,
    summary="Lock cut of an absent holder (IS-9; HSE Manager only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cut_personal_lock(
    event_id: uuid.UUID,
    body: LockCutInput,
    user: CurrentUser,
    db: DB,
) -> PersonalLockEventRead:
    return svc.cut(db, user, event_id, body)


@router.post(
    "/personal-lock-events/{event_id}/worker-informed",
    response_model=PersonalLockEventRead,
    summary="Record that the holder was informed of the cut",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_lock_cut_worker_informed(
    event_id: uuid.UUID,
    body: WorkerInformedInput,
    user: CurrentUser,
    db: DB,
) -> PersonalLockEventRead:
    return svc.worker_informed(db, user, event_id, body)


@router.get(
    "/projects/{project_id}/locks",
    response_model=LockPage,
    summary="Lock register",
    responses=error_responses(401, 403, 404, 422),
)
def list_locks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    lock_type: Annotated[list[LockType] | None, Query()] = None,
    status_: Annotated[list[LockStatus] | None, Query(alias="status")] = None,
    holder_worker_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> LockPage:
    return svc.list_locks(
        db, user, project_id, pg.page, pg.page_size, lock_type, status_, holder_worker_id, q
    )


@router.post(
    "/projects/{project_id}/locks",
    response_model=LockRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a lock (lock_no unique → 409)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_lock(project_id: uuid.UUID, body: LockCreate, user: CurrentUser, db: DB) -> LockRead:
    return svc.create_lock(db, user, project_id, body)


@router.patch(
    "/locks/{lock_id}",
    response_model=LockRead,
    summary="Edit a lock (personal lock holder)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_lock(lock_id: uuid.UUID, body: LockUpdate, user: CurrentUser, db: DB) -> LockRead:
    return svc.update_lock(db, user, lock_id, body)


@router.post(
    "/locks/{lock_id}/lost",
    response_model=LockRead,
    summary="Report a lock lost (IS-11: linked permits suspended isolation_breach)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def report_lock_lost(
    lock_id: uuid.UUID,
    body: LockLostInput,
    user: CurrentUser,
    db: DB,
) -> LockRead:
    return svc.report_lost(db, user, lock_id, body)
