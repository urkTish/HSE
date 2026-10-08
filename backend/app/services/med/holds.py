"""Fitness holds and referrals (§3.7, §3.8, FH, RF).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import (
    FitnessHoldPage,
    FitnessHoldRead,
    FitnessReferralPage,
    FitnessReferralRead,
)


def list_holds(*_: Any) -> FitnessHoldPage:
    raise not_implemented()


def create_manual(*_: Any) -> FitnessHoldRead:
    raise not_implemented()


def read_hold(*_: Any) -> FitnessHoldRead:
    raise not_implemented()


def cancel_hold(*_: Any) -> FitnessHoldRead:
    raise not_implemented()


def release_hold(*_: Any) -> FitnessHoldRead:
    raise not_implemented()


def list_referrals(*_: Any) -> FitnessReferralPage:
    raise not_implemented()


def create_referral(*_: Any) -> FitnessReferralRead:
    raise not_implemented()


def read_referral(*_: Any) -> FitnessReferralRead:
    raise not_implemented()


def cancel_referral(*_: Any) -> FitnessReferralRead:
    raise not_implemented()
