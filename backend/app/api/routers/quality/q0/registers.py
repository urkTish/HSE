"""Q0 HTTP routes: criteria library, systems, customers, suppliers and the M&TE register
(spec 8-quality §A.6, §A.8.1–§A.8.4)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.common import (
    QCalStatus,
    QCriterionStatus,
    QMteStatus,
    QMteType,
    QProfileScope,
    QSupplierCategory,
    QSupplierStatus,
)
from app.schemas.quality.q0 import (
    QAccreditationCreate,
    QCriterionCreate,
    QCriterionPage,
    QCriterionRead,
    QCriterionTransition,
    QCriterionUpdate,
    QCustomerCreate,
    QCustomerRead,
    QCustomerUpdate,
    QEvaluateRead,
    QEvaluateRequest,
    QMteCreate,
    QMtePage,
    QMteRead,
    QMteUpdate,
    QMteUsageCreate,
    QMteUsageRead,
    QSupplierCreate,
    QSupplierPage,
    QSupplierRead,
    QSupplierTransition,
    QSupplierUpdate,
    QSystemCreate,
    QSystemRead,
    QSystemUpdate,
)
from app.services.quality import criteria, customers, mte, suppliers, systems

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


# ---- criteria ------------------------------------------------------------------------------------


@router.get(
    "/quality/criteria",
    response_model=QCriterionPage,
    summary="Acceptance criteria library (org-wide, versioned)",
    responses=E,
)
def q_list_criteria(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    code: str | None = None,
    status_: Annotated[list[QCriterionStatus] | None, Query(alias="status")] = None,
    profile: QProfileScope | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return criteria.list_page(
        db, user, pg.page, pg.page_size, code=code, statuses=status_, profile=profile, q=q
    )


@router.post(
    "/quality/criteria",
    response_model=QCriterionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a criterion draft (240)",
    responses=E,
)
def q_create_criterion(body: QCriterionCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return criteria.create(db, user, body.model_dump())


@router.get(
    "/quality/criteria/{criterion_id}",
    response_model=QCriterionRead,
    summary="One criterion version",
    responses=E,
)
def q_get_criterion(criterion_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return criteria.read_one(db, user, criterion_id)


@router.patch(
    "/quality/criteria/{criterion_id}",
    response_model=QCriterionRead,
    summary="Edit a Draft (240; other states → 409 CRITERION_IMMUTABLE)",
    responses=E,
)
def q_update_criterion(
    criterion_id: uuid.UUID, body: QCriterionUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return criteria.update(db, user, criterion_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/criteria/{criterion_id}/new-version",
    response_model=QCriterionRead,
    status_code=status.HTTP_201_CREATED,
    summary="New Draft version (240)",
    responses=E,
)
def q_criterion_new_version(criterion_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return criteria.new_version(db, user, criterion_id)


@router.post(
    "/quality/criteria/{criterion_id}/transitions",
    response_model=QCriterionRead,
    summary="Publish or retire (239)",
    responses=E,
)
def q_criterion_transition(
    criterion_id: uuid.UUID, body: QCriterionTransition, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return criteria.transition(db, user, criterion_id, body.action, body.reason)


@router.post(
    "/quality/criteria/{criterion_id}/evaluate",
    response_model=QEvaluateRead,
    summary="Evaluate a value against this version (Q-CRT-01)",
    responses=E,
)
def q_evaluate_criterion(
    criterion_id: uuid.UUID, body: QEvaluateRequest, user: CurrentUser, db: DB
) -> dict[str, Any]:
    values = {"value": body.value, "verdict": body.verdict, **body.params}
    return criteria.evaluate_api(db, user, criterion_id, values)


# ---- systems -------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/systems",
    response_model=list[QSystemRead],
    summary="Systems (construction register)",
    responses=E,
)
def q_list_systems(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return systems.list_systems(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/systems",
    response_model=QSystemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a system (239; logistics profile → 409 PROFILE_INACTIVE)",
    responses=E,
)
def q_create_system(
    project_id: uuid.UUID, body: QSystemCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return systems.create(db, user, project_id, body.model_dump())


@router.patch(
    "/quality/systems/{system_id}",
    response_model=QSystemRead,
    summary="Edit or archive / reactivate a system (239)",
    responses=E,
)
def q_update_system(
    system_id: uuid.UUID, body: QSystemUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return systems.update(db, user, system_id, body.model_dump(exclude_unset=True))


# ---- customers -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/customers",
    response_model=list[QCustomerRead],
    summary="Customers (contacts only for 245 holders, P8-2)",
    responses=E,
)
def q_list_customers(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return customers.list_customers(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/customers",
    response_model=QCustomerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer (239 / 245)",
    responses=E,
)
def q_create_customer(
    project_id: uuid.UUID, body: QCustomerCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return customers.create(db, user, project_id, body.model_dump())


@router.patch(
    "/quality/customers/{customer_id}",
    response_model=QCustomerRead,
    summary="Edit a customer (239 / 245)",
    responses=E,
)
def q_update_customer(
    customer_id: uuid.UUID, body: QCustomerUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return customers.update(db, user, customer_id, body.model_dump(exclude_unset=True))


# ---- suppliers -----------------------------------------------------------------------------------


@router.get(
    "/quality/suppliers",
    response_model=QSupplierPage,
    summary="Supplier master (org-wide; contacts only for 278 holders)",
    responses=E,
)
def q_list_suppliers(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QSupplierStatus] | None, Query(alias="status")] = None,
    category: QSupplierCategory | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return suppliers.list_page(
        db, user, pg.page, pg.page_size, statuses=status_, category=category, q=q
    )


@router.post(
    "/quality/suppliers",
    response_model=QSupplierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a supplier (278)",
    responses=E,
)
def q_create_supplier(body: QSupplierCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return suppliers.create(db, user, body.model_dump())


@router.get(
    "/quality/suppliers/{supplier_id}",
    response_model=QSupplierRead,
    summary="One supplier",
    responses=E,
)
def q_get_supplier(supplier_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return suppliers.read_one(db, user, supplier_id)


@router.patch(
    "/quality/suppliers/{supplier_id}",
    response_model=QSupplierRead,
    summary="Edit a supplier (278)",
    responses=E,
)
def q_update_supplier(
    supplier_id: uuid.UUID, body: QSupplierUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return suppliers.update(db, user, supplier_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/suppliers/{supplier_id}/accreditations",
    response_model=QSupplierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an accreditation (278)",
    responses=E,
)
def q_add_accreditation(
    supplier_id: uuid.UUID, body: QAccreditationCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return suppliers.add_accreditation(db, user, supplier_id, body.model_dump())


@router.post(
    "/quality/suppliers/{supplier_id}/transitions",
    response_model=QSupplierRead,
    summary="Supplier status (Q-SHR-01; RPM supplier.approve / .suspend on project_id)",
    responses=E,
)
def q_supplier_transition(
    supplier_id: uuid.UUID, body: QSupplierTransition, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return suppliers.transition(
        db, user, supplier_id, body.to_status, body.reason, body.project_id, body.condition
    )


# ---- M&TE ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/mte",
    response_model=QMtePage,
    summary="M&TE register (§A.8.4)",
    responses=E,
)
def q_list_mte(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    cal_status: Annotated[list[QCalStatus] | None, Query()] = None,
    mte_type: QMteType | None = None,
    status_: Annotated[QMteStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return mte.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        cal_statuses=cal_status,
        mte_type=mte_type,
        status=status_,
        q=q,
    )


@router.post(
    "/projects/{project_id}/quality/mte",
    response_model=QMteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an instrument (261; cal_status unknown until Q2; duplicate "
    "manufacturer + serial → 422 MTE_SERIAL_DUPLICATE)",
    responses=E,
)
def q_create_mte(
    project_id: uuid.UUID, body: QMteCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return mte.create(db, user, project_id, body.model_dump())


@router.get("/quality/mte/{mte_id}", response_model=QMteRead, summary="One instrument", responses=E)
def q_get_mte(mte_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mte.read(db, mte.get_item(db, user, mte_id))


@router.patch(
    "/quality/mte/{mte_id}",
    response_model=QMteRead,
    summary="Edit an instrument (261)",
    responses=E,
)
def q_update_mte(mte_id: uuid.UUID, body: QMteUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mte.update(db, user, mte_id, body.model_dump(exclude_unset=True))


@router.get(
    "/quality/mte/{mte_id}/usage",
    response_model=list[QMteUsageRead],
    summary="Measurements made with the instrument (Q-SHR-04)",
    responses=E,
)
def q_list_mte_usage(mte_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return mte.usage_list(db, user, mte_id)


@router.post(
    "/quality/mte/{mte_id}/usage",
    response_model=QMteUsageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a use (warns or refuses MTE_NOT_CALIBRATED by mte_use_policy)",
    responses=E,
)
def q_record_mte_usage(
    mte_id: uuid.UUID, body: QMteUsageCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return mte.usage_api(db, user, mte_id, body.model_dump())
