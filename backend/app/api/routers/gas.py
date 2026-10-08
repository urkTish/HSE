"""Gas detectors, calibrations, bump tests and permit gas tests (spec 3-ptw §3.10, §5.4,
§6.2, §6.3)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.ptw_enums import DetectorStatus, GasTestResult, GasTestType
from app.schemas.gas import (
    BumpTestCreate,
    BumpTestList,
    BumpTestRead,
    CalibrationInput,
    DetectorCreate,
    DetectorPage,
    DetectorRead,
    DetectorRetireInput,
    DetectorUpdate,
    GasEvaluation,
    GasTestCreate,
    GasTestList,
    GasTestPage,
    GasTestPreview,
    GasTestRead,
    GasTestSupersede,
)
from app.services.ptw import gas as svc

router = APIRouter(tags=["gas-testing"])


@router.get(
    "/projects/{project_id}/gas-detectors",
    response_model=DetectorPage,
    summary="Gas detector register (calibration and bump-test status)",
    responses=error_responses(401, 403, 404, 422),
)
def list_gas_detectors(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[DetectorStatus] | None, Query(alias="status")] = None,
    engagement_id: uuid.UUID | None = None,
    calibration_due_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> DetectorPage:
    return svc.list_detectors(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        engagement_id,
        calibration_due_within_days,
        q,
    )


@router.post(
    "/projects/{project_id}/gas-detectors",
    response_model=DetectorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a gas detector (capability 91; serial unique → 409)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_gas_detector(
    project_id: uuid.UUID,
    body: DetectorCreate,
    user: CurrentUser,
    db: DB,
) -> DetectorRead:
    return svc.create_detector(db, user, project_id, body)


@router.get(
    "/gas-detectors/{detector_id}",
    response_model=DetectorRead,
    summary="Get a gas detector",
    responses=error_responses(401, 403, 404),
)
def get_gas_detector(detector_id: uuid.UUID, user: CurrentUser, db: DB) -> DetectorRead:
    return svc.read_detector(db, user, detector_id)


@router.patch(
    "/gas-detectors/{detector_id}",
    response_model=DetectorRead,
    summary="Edit a gas detector (capability 91)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_gas_detector(
    detector_id: uuid.UUID,
    body: DetectorUpdate,
    user: CurrentUser,
    db: DB,
) -> DetectorRead:
    return svc.update_detector(db, user, detector_id, body)


@router.post(
    "/gas-detectors/{detector_id}/calibrations",
    response_model=DetectorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a calibration (lifts calibration_overdue quarantine)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_detector_calibration(
    detector_id: uuid.UUID,
    body: CalibrationInput,
    user: CurrentUser,
    db: DB,
) -> DetectorRead:
    return svc.record_calibration(db, user, detector_id, body)


@router.get(
    "/gas-detectors/{detector_id}/bump-tests",
    response_model=BumpTestList,
    summary="Bump tests of a detector",
    responses=error_responses(401, 403, 404),
)
def list_bump_tests(
    detector_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BumpTestList:
    return svc.list_bumps(db, user, detector_id, date_from, date_to)


@router.post(
    "/gas-detectors/{detector_id}/bump-tests",
    response_model=BumpTestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a daily bump test (capability 90; fail → quarantined)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_bump_test(
    detector_id: uuid.UUID,
    body: BumpTestCreate,
    user: CurrentUser,
    db: DB,
) -> BumpTestRead:
    return svc.record_bump(db, user, detector_id, body)


@router.post(
    "/gas-detectors/{detector_id}/retire",
    response_model=DetectorRead,
    summary="Retire a detector (capability 91)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def retire_gas_detector(
    detector_id: uuid.UUID,
    body: DetectorRetireInput,
    user: CurrentUser,
    db: DB,
) -> DetectorRead:
    return svc.retire(db, user, detector_id, body)


@router.get(
    "/permits/{permit_id}/gas-tests",
    response_model=GasTestList,
    summary="Gas tests of a permit (newest first)",
    responses=error_responses(401, 403, 404),
)
def list_permit_gas_tests(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> GasTestList:
    return svc.list_for_permit(db, user, permit_id)


@router.post(
    "/permits/{permit_id}/gas-tests",
    response_model=GasTestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a gas test (capability 90; fail → suspension gas_test_failed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_gas_test(
    permit_id: uuid.UUID,
    body: GasTestCreate,
    user: CurrentUser,
    db: DB,
) -> GasTestRead:
    return svc.record(db, user, permit_id, body)


@router.post(
    "/permits/{permit_id}/gas-tests/preview",
    response_model=GasEvaluation,
    summary="Evaluate readings against the permit's limits (nothing stored)",
    responses=error_responses(401, 403, 404, 422),
)
def preview_gas_test(
    permit_id: uuid.UUID,
    body: GasTestPreview,
    user: CurrentUser,
    db: DB,
) -> GasEvaluation:
    return svc.preview(db, user, permit_id, body)


@router.get(
    "/projects/{project_id}/gas-tests",
    response_model=GasTestPage,
    summary="Gas test log of a project",
    responses=error_responses(401, 403, 404, 422),
)
def list_project_gas_tests(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    permit_id: uuid.UUID | None = None,
    detector_id: uuid.UUID | None = None,
    test_type: Annotated[list[GasTestType] | None, Query()] = None,
    result: GasTestResult | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> GasTestPage:
    return svc.list_project(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        permit_id,
        detector_id,
        test_type,
        result,
        date_from,
        date_to,
    )


@router.get(
    "/gas-tests/{gas_test_id}",
    response_model=GasTestRead,
    summary="Get a gas test",
    responses=error_responses(401, 403, 404),
)
def get_gas_test(gas_test_id: uuid.UUID, user: CurrentUser, db: DB) -> GasTestRead:
    return svc.read_test(db, user, gas_test_id)


@router.post(
    "/gas-tests/{gas_test_id}/supersede",
    response_model=GasTestRead,
    summary="Supersede an erroneous gas test with a reason (the new test is recorded separately)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def supersede_gas_test(
    gas_test_id: uuid.UUID,
    body: GasTestSupersede,
    user: CurrentUser,
    db: DB,
) -> GasTestRead:
    return svc.supersede(db, user, gas_test_id, body)
