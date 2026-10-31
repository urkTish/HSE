"""Q3 HTTP routes: receiving, holds, stock quality, returns, recalls and transport (spec
8-quality §D.2, §D.7–§D.9)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.q3 import (
    QFefoResult,
    QHoldReason,
    QHoldStatus,
    QLineDecision,
    QReceiptStatus,
    QTripStatus,
)
from app.schemas.quality.q3 import (
    Q3AnswersInput,
    Q3CommentInput,
    Q3CountCreate,
    Q3CountRead,
    Q3DamageCreate,
    Q3DamagePage,
    Q3DamageRead,
    Q3DispatchInput,
    Q3ExpiryHoldInput,
    Q3FefoCreate,
    Q3FefoPage,
    Q3FefoRead,
    Q3GradeInput,
    Q3HoldCreate,
    Q3HoldDecide,
    Q3HoldLinesInput,
    Q3HoldPage,
    Q3HoldRead,
    Q3LineDecide,
    Q3NearExpiry,
    Q3OutcomeInput,
    Q3PodCreate,
    Q3PreloadInput,
    Q3ReasonInput,
    Q3RecallClose,
    Q3RecallContactUpdate,
    Q3RecallCreate,
    Q3RecallListItem,
    Q3RecallRead,
    Q3ReceiptCreate,
    Q3ReceiptHeader,
    Q3ReceiptLineInput,
    Q3ReceiptPage,
    Q3ReceiptRead,
    Q3ReturnCreate,
    Q3ReturnPage,
    Q3ReturnRead,
    Q3SegregationInput,
    Q3ShipmentRead,
    Q3SnapshotRead,
    Q3ThroughputInput,
    Q3ThroughputRead,
    Q3TraceConfirm,
    Q3TripCreate,
    Q3TripPage,
    Q3TripRead,
)
from app.services.quality.q3 import holds, recalls, receiving, returns, stock, transport

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
P = "/projects/{project_id}/quality"


# ---- receiving (§D.2) --------------------------------------------------------------------------


@router.get(
    P + "/receipts", response_model=Q3ReceiptPage, summary="Receiving register", responses=E
)
def q3_list_receipts(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    customer_id: uuid.UUID | None = None,
    decision: QLineDecision | None = None,
    deviation: bool | None = None,
    status_: Annotated[QReceiptStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    return receiving.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        customer_id=customer_id,
        decision=decision,
        deviation=deviation,
        status=status_,
        q=q,
    )


@router.post(
    P + "/receipts",
    response_model=Q3ReceiptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a receiving inspection (264; logistics profile)",
    responses=E,
)
def q3_create_receipt(
    project_id: uuid.UUID, body: Q3ReceiptCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    data = body.model_dump()
    data["lines"] = [x.model_dump(exclude_unset=True) for x in body.lines]
    return receiving.create(db, user, project_id, data)


@router.get(
    "/quality/receipts/{receipt_id}",
    response_model=Q3ReceiptRead,
    summary="One receipt",
    responses=E,
)
def q3_get_receipt(receipt_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, _ = receiving.get_receipt(db, user, receipt_id)
    return receiving.read(db, user, r)


@router.patch(
    "/quality/receipts/{receipt_id}",
    response_model=Q3ReceiptRead,
    summary="Edit the header (warnings DOCK_DWELL_LONG, SEAL_MISMATCH)",
    responses=E,
)
def q3_update_receipt(
    receipt_id: uuid.UUID, body: Q3ReceiptHeader, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.update(db, user, receipt_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/receipts/{receipt_id}/lines",
    response_model=Q3ReceiptRead,
    summary="Add a line (422 MTE_REQUIRED for temperature-controlled classes)",
    responses=E,
)
def q3_add_line(
    receipt_id: uuid.UUID, body: Q3ReceiptLineInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.save_line(db, user, receipt_id, None, body.model_dump(exclude_unset=True))


@router.patch(
    "/quality/receipts/{receipt_id}/lines/{line_id}",
    response_model=Q3ReceiptRead,
    summary="Edit an undecided line",
    responses=E,
)
def q3_update_line(
    receipt_id: uuid.UUID, line_id: uuid.UUID, body: Q3ReceiptLineInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.save_line(db, user, receipt_id, line_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/receipts/{receipt_id}/vehicle-check",
    response_model=Q3ReceiptRead,
    summary="Vehicle check QRCV (6d engine)",
    responses=E,
)
def q3_vehicle_check(
    receipt_id: uuid.UUID, body: Q3AnswersInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.vehicle_check(
        db, user, receipt_id, {"answers": body.answers, "template_code": body.template_code}
    )


@router.post(
    "/quality/receipts/{receipt_id}/inspect",
    response_model=Q3ReceiptRead,
    summary="Draft → Inspected (number assigned, proposals computed)",
    responses=E,
)
def q3_inspect_receipt(receipt_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return receiving.inspect(db, user, receipt_id)


@router.post(
    "/quality/receipts/{receipt_id}/cancel",
    response_model=Q3ReceiptRead,
    summary="Cancel a receipt without decided lines",
    responses=E,
)
def q3_cancel_receipt(
    receipt_id: uuid.UUID, body: Q3ReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.cancel(db, user, receipt_id, body.model_dump())


@router.post(
    "/quality/receipt-lines/{line_id}/decide",
    response_model=Q3ReceiptRead,
    summary="Record the line decision (RPM receipt.deviation / receipt.reject; 422 "
    "DECISION_BETTER_THAN_CRITERIA, OWNER_DECISION_REQUIRED, REJECT_NEEDS_NCR_OR_CLAIM)",
    responses=E,
)
def q3_decide_line(
    line_id: uuid.UUID, body: Q3LineDecide, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return receiving.decide(db, user, line_id, body.model_dump())


# ---- holds (§D.7.3) ----------------------------------------------------------------------------


@router.get(
    P + "/holds",
    response_model=Q3HoldPage,
    summary="Hold register with ageing and blockers",
    responses=E,
)
def q3_list_holds(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QHoldStatus] | None, Query(alias="status")] = None,
    reason: QHoldReason | None = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    return holds.list_page(
        db, user, project_id, pg.page, pg.page_size, statuses=status_, reason=reason, q=q
    )


@router.get(
    P + "/holds/export.csv",
    summary="WMS hold export (owner, sku, batch, location, qty, hold no, status; Q-HLD-08)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}, **E},
)
def q3_export_holds(project_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    return Response(
        holds.export_csv(db, user, project_id),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="holds.csv"'},
    )


@router.post(
    P + "/holds",
    response_model=Q3HoldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place a hold (270; Warehouse QC may place)",
    responses=E,
)
def q3_create_hold(
    project_id: uuid.UUID, body: Q3HoldCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.create_api(db, user, project_id, body.model_dump())


@router.get("/quality/holds/{hold_id}", response_model=Q3HoldRead, summary="One hold", responses=E)
def q3_get_hold(hold_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    h, _ = holds.get_hold(db, user, hold_id)
    return holds.read(db, user, h)


@router.post(
    "/quality/holds/{hold_id}/lines",
    response_model=Q3HoldRead,
    summary="Add lines to a zone-level hold (Q-HLD-02)",
    responses=E,
)
def q3_hold_lines(
    hold_id: uuid.UUID, body: Q3HoldLinesInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.add_lines(db, user, hold_id, body.model_dump())


@router.post(
    "/quality/holds/{hold_id}/segregation",
    response_model=Q3HoldRead,
    summary="Record segregation with a photo (Q-HLD-03)",
    responses=E,
)
def q3_hold_segregation(
    hold_id: uuid.UUID, body: Q3SegregationInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.segregate(db, user, hold_id, body.model_dump())


@router.post(
    "/quality/holds/{hold_id}/wms-confirmed",
    response_model=Q3HoldRead,
    summary="Tick WMS hold confirmed",
    responses=E,
)
def q3_hold_wms(hold_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return holds.wms_confirmed(db, user, hold_id)


@router.post(
    "/quality/holds/{hold_id}/decide",
    response_model=Q3HoldRead,
    summary="Release or reject lines (RPM hold.release / hold.reject; 422 HOLD_RELEASE_BLOCKED, "
    "OWNER_DECISION_REQUIRED)",
    responses=E,
)
def q3_hold_decide(
    hold_id: uuid.UUID, body: Q3HoldDecide, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.decide(db, user, hold_id, body.model_dump())


@router.post(
    "/quality/holds/{hold_id}/close",
    response_model=Q3HoldRead,
    summary="Close a hold (every rejected line evidenced, Q-HLD-06)",
    responses=E,
)
def q3_hold_close(hold_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return holds.close(db, user, hold_id)


@router.post(
    "/quality/hold-lines/{line_id}/rehold",
    response_model=Q3HoldRead,
    summary="Hold a released line again",
    responses=E,
)
def q3_hold_rehold(
    line_id: uuid.UUID, body: Q3ReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.rehold(db, user, line_id, body.model_dump())


@router.post(
    "/quality/hold-lines/{line_id}/outcome",
    response_model=Q3HoldRead,
    summary="Final outcome of a rejected line with evidence (269)",
    responses=E,
)
def q3_hold_outcome(
    line_id: uuid.UUID, body: Q3OutcomeInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return holds.outcome(db, user, line_id, body.model_dump())


# ---- stock (§D.7) ------------------------------------------------------------------------------


@router.get(
    P + "/stock-snapshots",
    response_model=list[Q3SnapshotRead],
    summary="Imported stock snapshots",
    responses=E,
)
def q3_list_snapshots(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return stock.list_snapshots(db, user, project_id)


@router.get(
    P + "/near-expiry",
    response_model=Q3NearExpiry,
    summary="Expired and near-expiry lines of the latest snapshot (Q-STK-02)",
    responses=E,
)
def q3_near_expiry(
    project_id: uuid.UUID, user: CurrentUser, db: DB, site_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return stock.near_expiry(db, user, project_id, site_id)


@router.post(
    P + "/near-expiry/hold",
    response_model=Q3HoldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place an expiry hold on stock lines",
    responses=E,
)
def q3_expiry_hold(
    project_id: uuid.UUID, body: Q3ExpiryHoldInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return stock.place_expiry_hold(db, user, project_id, body.model_dump())


@router.get(
    P + "/fefo-checks", response_model=Q3FefoPage, summary="FEFO / FIFO checks", responses=E
)
def q3_list_fefo(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    result: QFefoResult | None = None,
) -> dict[str, Any]:
    return stock.list_fefo(db, user, project_id, pg.page, pg.page_size, result)


@router.post(
    P + "/fefo-checks",
    response_model=Q3FefoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a FEFO check (eligible earliest computed, Q-STK-04)",
    responses=E,
)
def q3_create_fefo(
    project_id: uuid.UUID, body: Q3FefoCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return stock.create_fefo(db, user, project_id, body.model_dump())


@router.post(
    "/quality/fefo-checks/{check_id}/confirm",
    response_model=Q3FefoRead,
    summary="Confirm an 'other' exception (266, Q-STK-05)",
    responses=E,
)
def q3_confirm_fefo(check_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return stock.confirm_fefo(db, user, check_id)


@router.get(
    P + "/damage-reports", response_model=Q3DamagePage, summary="Damage reports", responses=E
)
def q3_list_damage(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> dict[str, Any]:
    return stock.list_damage(db, user, project_id, pg.page, pg.page_size)


@router.post(
    P + "/damage-reports",
    response_model=Q3DamageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Report damage (a hold unless destroyed on the spot, Q-STK-07)",
    responses=E,
)
def q3_create_damage(
    project_id: uuid.UUID, body: Q3DamageCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return stock.create_damage(db, user, project_id, body.model_dump())


@router.get(
    P + "/cycle-counts",
    response_model=list[Q3CountRead],
    summary="Cycle counts with IRA",
    responses=E,
)
def q3_list_counts(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return stock.list_counts(db, user, project_id)


@router.post(
    P + "/cycle-counts",
    response_model=Q3CountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a cycle count (Q-STK-09)",
    responses=E,
)
def q3_create_count(
    project_id: uuid.UUID, body: Q3CountCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return stock.create_count_api(db, user, project_id, body.model_dump())


@router.get(
    P + "/throughput",
    response_model=list[Q3ThroughputRead],
    summary="Units handled per site and month (Q-STK-03)",
    responses=E,
)
def q3_list_throughput(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return stock.list_throughput(db, user, project_id)


@router.put(
    P + "/throughput",
    response_model=Q3ThroughputRead,
    summary="Enter a month's throughput",
    responses=E,
)
def q3_put_throughput(
    project_id: uuid.UUID, body: Q3ThroughputInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return stock.upsert_throughput(db, user, project_id, body.model_dump())


# ---- returns -----------------------------------------------------------------------------------


@router.get(P + "/returns", response_model=Q3ReturnPage, summary="Returns", responses=E)
def q3_list_returns(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> dict[str, Any]:
    return returns.list_returns(db, user, project_id, pg.page, pg.page_size)


@router.post(
    P + "/returns",
    response_model=Q3ReturnRead,
    status_code=status.HTTP_201_CREATED,
    summary="Receive a return (269)",
    responses=E,
)
def q3_create_return(
    project_id: uuid.UUID, body: Q3ReturnCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return returns.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/returns/{return_id}", response_model=Q3ReturnRead, summary="One return", responses=E
)
def q3_get_return(return_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, _ = returns.get_return(db, user, return_id)
    return returns.read(db, user, r)


@router.post(
    "/quality/returns/{return_id}/inspection",
    response_model=Q3ReturnRead,
    summary="Return inspection checklist QRET",
    responses=E,
)
def q3_return_inspection(
    return_id: uuid.UUID, body: Q3AnswersInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return returns.inspection(db, user, return_id, {"answers": body.answers})


@router.post(
    "/quality/returns/{return_id}/grade",
    response_model=Q3ReturnRead,
    summary="Grade lines A–D (422 COLD_RETURN_NO_HISTORY)",
    responses=E,
)
def q3_grade_return(
    return_id: uuid.UUID, body: Q3GradeInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return returns.grade(db, user, return_id, body.model_dump())


@router.post(
    "/quality/returns/{return_id}/confirm",
    response_model=Q3ReturnRead,
    summary="Confirm grades (RPM return.disposition; grade C → hold)",
    responses=E,
)
def q3_confirm_return(
    return_id: uuid.UUID, body: Q3CommentInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return returns.confirm(db, user, return_id, body.model_dump())


# ---- recalls -----------------------------------------------------------------------------------


@router.get(
    P + "/recalls",
    response_model=list[Q3RecallListItem],
    summary="Recalls and mock recalls",
    responses=E,
)
def q3_list_recalls(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return recalls.list_recalls(db, user, project_id)


@router.post(
    P + "/recalls",
    response_model=Q3RecallRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open a recall (271; real recalls hold stock and open a critical NCR)",
    responses=E,
)
def q3_create_recall(
    project_id: uuid.UUID, body: Q3RecallCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return recalls.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/recalls/{recall_id}",
    response_model=Q3RecallRead,
    summary="One recall with its live trace",
    responses=E,
)
def q3_get_recall(recall_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, _ = recalls.get_recall(db, user, recall_id)
    return recalls.read(db, user, r)


@router.post(
    "/quality/recalls/{recall_id}/trace",
    response_model=Q3RecallRead,
    summary="Confirm the trace (Open → Traced)",
    responses=E,
)
def q3_confirm_trace(
    recall_id: uuid.UUID, body: Q3TraceConfirm, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return recalls.confirm_trace(db, user, recall_id, body.model_dump())


@router.post(
    "/quality/recalls/{recall_id}/recover",
    response_model=Q3RecallRead,
    summary="Start recovery (real recalls)",
    responses=E,
)
def q3_recover(recall_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return recalls.recover(db, user, recall_id)


@router.patch(
    "/quality/recall-contacts/{item_id}",
    response_model=Q3RecallRead,
    summary="Record a consignee contact",
    responses=E,
)
def q3_recall_contact(
    item_id: uuid.UUID, body: Q3RecallContactUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return recalls.update_item(db, user, item_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/recalls/{recall_id}/close",
    response_model=Q3RecallRead,
    summary="Close (RPM recall.close; 422 RECALL_TARGET_NOT_MET)",
    responses=E,
)
def q3_close_recall(
    recall_id: uuid.UUID, body: Q3RecallClose, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return recalls.close(db, user, recall_id, body.model_dump())


@router.post(
    "/quality/recalls/{recall_id}/cancel",
    response_model=Q3RecallRead,
    summary="Cancel a recall (RPM recall.close)",
    responses=E,
)
def q3_cancel_recall(
    recall_id: uuid.UUID, body: Q3ReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return recalls.cancel(db, user, recall_id, body.model_dump())


# ---- transport ---------------------------------------------------------------------------------


@router.get(
    P + "/shipments", response_model=list[Q3ShipmentRead], summary="Imported shipments", responses=E
)
def q3_list_shipments(
    project_id: uuid.UUID, user: CurrentUser, db: DB, unassigned: bool = False
) -> list[dict[str, Any]]:
    return transport.list_shipments(db, user, project_id, unassigned)


@router.get(P + "/trips", response_model=Q3TripPage, summary="Trip board", responses=E)
def q3_list_trips(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[QTripStatus | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return transport.list_trips(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    P + "/trips",
    response_model=Q3TripRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan a trip (272; 422 INCOMPATIBLE_LOAD; warning VEHICLE_NOT_READY)",
    responses=E,
)
def q3_create_trip(
    project_id: uuid.UUID, body: Q3TripCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return transport.create(db, user, project_id, body.model_dump())


@router.get("/quality/trips/{trip_id}", response_model=Q3TripRead, summary="One trip", responses=E)
def q3_get_trip(trip_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    t, _ = transport.get_trip(db, user, trip_id)
    return transport.read(db, user, t)


@router.post(
    "/quality/trips/{trip_id}/preload",
    response_model=Q3TripRead,
    summary="Pre-load check QRPL and loading temperatures",
    responses=E,
)
def q3_trip_preload(
    trip_id: uuid.UUID, body: Q3PreloadInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return transport.preload(db, user, trip_id, {**body.model_dump(), "answers": body.answers})


@router.post(
    "/quality/trips/{trip_id}/dispatch",
    response_model=Q3TripRead,
    summary="Dispatch (422 PRELOAD_FAILED / OVERRIDE_NOT_ALLOWED; override by RPM "
    "trip.dispatch_override)",
    responses=E,
)
def q3_trip_dispatch(
    trip_id: uuid.UUID, body: Q3DispatchInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return transport.dispatch(db, user, trip_id, body.model_dump())


@router.post(
    "/quality/trips/{trip_id}/pods",
    response_model=Q3TripRead,
    status_code=status.HTTP_201_CREATED,
    summary="Proof of delivery of one shipment",
    responses=E,
)
def q3_trip_pod(trip_id: uuid.UUID, body: Q3PodCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return transport.add_pod(db, user, trip_id, body.model_dump())


@router.post(
    "/quality/trips/{trip_id}/deliver",
    response_model=Q3TripRead,
    summary="Dispatched → Delivered (422 POD_REQUIRED)",
    responses=E,
)
def q3_trip_deliver(trip_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return transport.deliver(db, user, trip_id)


@router.post(
    "/quality/trips/{trip_id}/cancel",
    response_model=Q3TripRead,
    summary="Cancel a planned trip",
    responses=E,
)
def q3_trip_cancel(
    trip_id: uuid.UUID, body: Q3ReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return transport.cancel(db, user, trip_id, body.model_dump())
