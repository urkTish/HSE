"""Fitness assessments, verification and scans (§3.6, §4.3, FA, FV).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.attachments import SignedUrlRead
from app.schemas.medical import (
    FitnessAssessmentPage,
    FitnessAssessmentRead,
    FitnessVerificationList,
    FitnessVerificationRead,
)


def list_assessments(*_: Any) -> FitnessAssessmentPage:
    raise not_implemented()


def create(*_: Any) -> FitnessAssessmentRead:
    raise not_implemented()


def read(*_: Any) -> FitnessAssessmentRead:
    raise not_implemented()


def update(*_: Any) -> FitnessAssessmentRead:
    raise not_implemented()


def transition(*_: Any) -> FitnessAssessmentRead:
    raise not_implemented()


def list_verifications(*_: Any) -> FitnessVerificationList:
    raise not_implemented()


def verify(*_: Any) -> FitnessVerificationRead:
    raise not_implemented()


def scan_url(*_: Any) -> SignedUrlRead:
    raise not_implemented()
