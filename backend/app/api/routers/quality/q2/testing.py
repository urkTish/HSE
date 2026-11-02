"""Q2 routes: test types, test requests with specimens and results, and concrete pours
(spec 8-quality §C.2)."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.routers.quality.q2.common import paper, with_warnings
from app.core.errors import error_responses
from app.core.quality.common import QProfileScope
from app.core.quality.q2 import QPourStatus, QTestStatus, QTestTypeStatus, QTestVerdict
from app.schemas.quality.q2 import (
    QPourClose,
    QPourCreate,
    QPourPage,
    QPourRead,
    QPourStart,
    QReasonBody,
    QSpecimenCalendar,
    QTestAmend,
    QTestCreate,
    QTestDeliver,
    QTestNcrDecision,
    QTestPage,
    QTestRead,
    QTestResults,
    QTestSample,
    QTestSpecimens,
    QTestTypeCreate,
    QTestTypeNewVersion,
    QTestTypeRead,
    QTestTypeTransition,
    QTestTypeUpdate,
    QTestUpdate,
    QTestVerify,
)
from app.services.quality.q2 import pours, testing

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


# ---- test types ----------------------------------------------------------------------------------


@router.get(
    "/quality/test-types",
    response_model=list[QTestTypeRead],
    summary="Test types (versioned data, Q-TST-01)",
    responses=E,
)
def q_list_test_types(
    user: CurrentUser,
    db: DB,
    status_: Annotated[QTestTypeStatus | None, Query(alias="status")] = None,
    profile: QProfileScope | None = None,
    project_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    return testing.list_types(db, user, status_, profile, project_id)


@router.post(
    "/quality/test-types",
    response_model=QTestTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="New test type draft (240)",
    responses=E,
)
def q_create_test_type(body: QTestTypeCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return testing.create_type(db, user, body.model_dump())


@router.get(
    "/quality/test-types/{type_id}",
    response_model=QTestTypeRead,
    summary="One test type version",
    responses=E,
)
def q_get_test_type(type_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    testing.list_types(db, user, None, None, None)  # permission
    return testing.type_read(testing.get_type(db, type_id))


@router.patch(
    "/quality/test-types/{type_id}",
    response_model=QTestTypeRead,
    summary="Edit a draft (240)",
    responses=E,
)
def q_update_test_type(
    type_id: uuid.UUID, body: QTestTypeUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.update_type(db, user, type_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/test-types/{type_id}/new-version",
    response_model=QTestTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="New draft version (optionally a project's own)",
    responses=E,
)
def q_test_type_version(
    type_id: uuid.UUID, body: QTestTypeNewVersion, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.new_type_version(db, user, type_id, body.project_id)


@router.post(
    "/quality/test-types/{type_id}/transitions",
    response_model=QTestTypeRead,
    summary="Publish or retire (239)",
    responses=E,
)
def q_test_type_transition(
    type_id: uuid.UUID, body: QTestTypeTransition, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.type_transition(db, user, type_id, body.action, body.reason)


# ---- test requests -------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/tests",
    response_model=QTestPage,
    summary="Test requests",
    responses=E,
)
def q_list_tests(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QTestStatus] | None, Query(alias="status")] = None,
    verdict: QTestVerdict | None = None,
    test_type: Annotated[str | None, Query(max_length=16)] = None,
    pour_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return testing.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        verdict=verdict,
        test_type=test_type,
        pour_id=pour_id,
        q=q,
    )


@router.get(
    "/projects/{project_id}/quality/specimen-calendar",
    response_model=QSpecimenCalendar,
    summary="Specimens due today, overdue and in the next 7 days",
    responses=E,
)
def q_specimen_calendar(
    project_id: uuid.UUID, user: CurrentUser, db: DB, on: date | None = None
) -> dict[str, Any]:
    return testing.specimen_calendar(db, user, project_id, on)


@router.post(
    "/projects/{project_id}/quality/tests",
    response_model=QTestRead,
    status_code=status.HTTP_201_CREATED,
    summary="New test request (257; Q-TST-02 lab checks)",
    responses=E,
)
def q_create_test(
    project_id: uuid.UUID, body: QTestCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    t, w = testing.create(db, user, project_id, body.model_dump())
    return with_warnings(testing.read(db, user, t), w)


@router.get(
    "/quality/tests/{test_id}",
    response_model=QTestRead,
    summary="One test request with specimens, verdict and history",
    responses=E,
)
def q_get_test(test_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return testing.read(db, user, testing.get_test(db, user, test_id))


@router.patch(
    "/quality/tests/{test_id}",
    response_model=QTestRead,
    summary="Edit details (after verification → 409 RESULT_VERIFIED)",
    responses=E,
)
def q_update_test(
    test_id: uuid.UUID, body: QTestUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.read(
        db, user, testing.update(db, user, test_id, body.model_dump(exclude_unset=True))
    )


@router.post(
    "/quality/tests/{test_id}/sample",
    response_model=QTestRead,
    summary="Requested → Sampled (M&TE usage; specimens and due dates)",
    responses=E,
)
def q_sample_test(
    test_id: uuid.UUID, body: QTestSample, user: CurrentUser, db: DB
) -> dict[str, Any]:
    t, w = testing.sample(db, user, test_id, body.model_dump())
    return with_warnings(testing.read(db, user, t), w)


@router.post(
    "/quality/tests/{test_id}/deliver",
    response_model=QTestRead,
    summary="Sampled → At Lab",
    responses=E,
)
def q_deliver_test(
    test_id: uuid.UUID, body: QTestDeliver, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.read(db, user, testing.deliver(db, user, test_id, body.delivered_on))


@router.put(
    "/quality/tests/{test_id}/specimens",
    response_model=QTestRead,
    summary="Specimen results while at the lab (early ages are indicative, Q-TST-07)",
    responses=E,
)
def q_test_specimens(
    test_id: uuid.UUID, body: QTestSpecimens, user: CurrentUser, db: DB
) -> dict[str, Any]:
    t, w = testing.record_specimens(db, user, test_id, [s.model_dump() for s in body.specimens])
    return with_warnings(testing.read(db, user, t), w)


@router.post(
    "/quality/tests/{test_id}/results",
    response_model=QTestRead,
    summary="At Lab → Results Entered (Q-TST-04; verdict; Q-TST-06 NCR)",
    responses=E,
)
def q_test_results(
    test_id: uuid.UUID, body: QTestResults, user: CurrentUser, db: DB
) -> dict[str, Any]:
    data = body.model_dump()
    data["specimens"] = list(data["specimens"])
    t, w, extra = testing.enter_results(db, user, test_id, data)
    return with_warnings(testing.read(db, user, t), w, **extra)


@router.post(
    "/quality/tests/{test_id}/verify",
    response_model=QTestRead,
    summary="Verify or return (258 + RPM test_request.verify; Q-TST-05)",
    responses=E,
)
def q_verify_test(
    test_id: uuid.UUID, body: QTestVerify, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.read(
        db, user, testing.verify(db, user, test_id, body.decision, body.comment, paper(body))
    )


@router.post(
    "/quality/tests/{test_id}/amend",
    response_model=QTestRead,
    summary="Amend verified results (Q-TST-09; the original is kept)",
    responses=E,
)
def q_amend_test(test_id: uuid.UUID, body: QTestAmend, user: CurrentUser, db: DB) -> dict[str, Any]:
    t, w, extra = testing.amend(db, user, test_id, body.model_dump())
    return with_warnings(testing.read(db, user, t), w, **extra)


@router.post(
    "/quality/tests/{test_id}/ncr-decision",
    response_model=QTestRead,
    summary="Prompt mode: raise the NCR or record why not (Q-TST-06)",
    responses=E,
)
def q_test_ncr_decision(
    test_id: uuid.UUID, body: QTestNcrDecision, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.read(
        db, user, testing.ncr_decision(db, user, test_id, body.raise_ncr, body.reason)
    )


@router.post(
    "/quality/tests/{test_id}/cancel",
    response_model=QTestRead,
    summary="Cancel (Requested / Sampled; reason ≥ 20)",
    responses=E,
)
def q_cancel_test(
    test_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return testing.read(db, user, testing.cancel(db, user, test_id, body.reason))


@router.post(
    "/quality/tests/{test_id}/void",
    response_model=QTestRead,
    summary="Void (244; reason ≥ 20)",
    responses=E,
)
def q_void_test(test_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    return testing.read(db, user, testing.void(db, user, test_id, body.reason))


# ---- pours ---------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/pours",
    response_model=QPourPage,
    summary="Concrete pours with sets required vs taken",
    responses=E,
)
def q_list_pours(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[QPourStatus | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return pours.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    "/projects/{project_id}/quality/pours",
    response_model=QPourRead,
    status_code=status.HTTP_201_CREATED,
    summary="New pour (257; construction)",
    responses=E,
)
def q_create_pour(
    project_id: uuid.UUID, body: QPourCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, w = pours.create(db, user, project_id, body.model_dump())
    return with_warnings(pours.read(db, user, x), w)


@router.get(
    "/quality/pours/{pour_id}",
    response_model=QPourRead,
    summary="One pour with the mix strength status",
    responses=E,
)
def q_get_pour(pour_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return pours.read(db, user, pours.get_pour(db, user, pour_id))


@router.post(
    "/quality/pours/{pour_id}/start",
    response_model=QPourRead,
    summary="Start (Q-TST-12 hold point)",
    responses=E,
)
def q_start_pour(pour_id: uuid.UUID, body: QPourStart, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = pours.start(db, user, pour_id, body.started_at)
    return with_warnings(pours.read(db, user, x), w)


@router.post(
    "/quality/pours/{pour_id}/close",
    response_model=QPourRead,
    summary="Close (POUR_SAMPLING_SHORT when sets are short)",
    responses=E,
)
def q_close_pour(pour_id: uuid.UUID, body: QPourClose, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = pours.close(db, user, pour_id, body.finished_at, body.ambient_temp_c)
    return with_warnings(pours.read(db, user, x), w)


@router.post(
    "/quality/pours/{pour_id}/cancel",
    response_model=QPourRead,
    summary="Cancel a planned pour",
    responses=E,
)
def q_cancel_pour(
    pour_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return pours.read(db, user, pours.cancel(db, user, pour_id, body.reason))
