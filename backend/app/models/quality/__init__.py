"""Phase 8 Quality tables (spec 8-quality §3.3): Q0 in `q0`, one stub module per wave-2 part
(`q1` … `q4`, each with its own `__all__`). Importing this package registers every Quality table on
`Base.metadata`, so Alembic autogenerate sees a part's tables as soon as the part adds them."""

from app.models.quality import q1, q2, q3, q4  # noqa: F401  (register the parts' tables)
from app.models.quality.q0 import (
    QAlert,
    QAlertAck,
    QComplaint,
    QCriterion,
    QCustomer,
    QLink,
    QMteItem,
    QMteUsage,
    QNcr,
    QNcrCost,
    QNcrLine,
    QNcrRca,
    QNumbering,
    QObservation,
    QPosition,
    QPositionHolder,
    QRpRule,
    QSettings,
    QSignoff,
    QSupplier,
    QSupplierAccreditation,
    QSystem,
)

__all__ = [
    "QAlert",
    "QAlertAck",
    "QComplaint",
    "QCriterion",
    "QCustomer",
    "QLink",
    "QMteItem",
    "QMteUsage",
    "QNcr",
    "QNcrCost",
    "QNcrLine",
    "QNcrRca",
    "QNumbering",
    "QObservation",
    "QPosition",
    "QPositionHolder",
    "QRpRule",
    "QSettings",
    "QSignoff",
    "QSupplier",
    "QSupplierAccreditation",
    "QSystem",
]
