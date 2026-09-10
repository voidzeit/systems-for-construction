"""Append-only human review and value state boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from .lifecycle import ValueStatus, VALUE_TRANSITIONS, transition


class ReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVOKED = "revoked"


@dataclass(frozen=True)
class Review:
    review_id: str
    target_id: str
    decision: ReviewDecision
    reviewer_id: str
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str | None = None
    supersedes_review_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Review":
        return cls(
            review_id=value.get("reviewId", ""),
            target_id=value.get("targetId", ""),
            decision=ReviewDecision(value.get("decision", "accepted")),
            reviewer_id=value.get("reviewerId", ""),
            reviewed_at=value.get("reviewedAt", datetime.now(timezone.utc).isoformat()),
            reason=value.get("reason"),
            supersedes_review_id=value.get("supersedesReviewId"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewId": self.review_id,
            "targetId": self.target_id,
            "decision": self.decision.value,
            "reviewerId": self.reviewer_id,
            "reviewedAt": self.reviewed_at,
            "reason": self.reason,
            "supersedesReviewId": self.supersedes_review_id,
        }


def current_review(reviews: Iterable[Review], target_id: str) -> Review | None:
    """Calculate current review without mutating or deleting history."""
    relevant = [review for review in reviews if review.target_id == target_id]
    revoked = {review.supersedes_review_id for review in relevant if review.decision is ReviewDecision.REVOKED}
    active = [review for review in relevant if review.decision is not ReviewDecision.REVOKED and review.review_id not in revoked]
    return active[-1] if active else None


@dataclass(frozen=True)
class ValueRecord:
    value_id: str
    work_package_id: str | None
    status: ValueStatus = ValueStatus.UNBUDGETED
    amount: float | None = None
    currency: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ValueRecord":
        return cls(
            value_id=value.get("valueId", ""),
            work_package_id=value.get("workPackageId"),
            status=ValueStatus(value.get("status", "Unbudgeted")),
            amount=value.get("amount"),
            currency=value.get("currency"),
            evidence_ids=tuple(value.get("evidenceIds", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valueId": self.value_id,
            "workPackageId": self.work_package_id,
            "status": self.status.value,
            "amount": self.amount,
            "currency": self.currency,
            "evidenceIds": list(self.evidence_ids),
        }

    def advance(self, target: ValueStatus, *, evidence_ids: tuple[str, ...] = ()) -> "ValueRecord":
        transition(self.status, target, VALUE_TRANSITIONS)
        if target in {ValueStatus.EARNED, ValueStatus.CERTIFIED, ValueStatus.BILLED, ValueStatus.APPROVED_FOR_PAYMENT, ValueStatus.PAID, ValueStatus.COLLECTED} and not (self.evidence_ids or evidence_ids):
            raise ValueError("value recognition requires evidence")
        return ValueRecord(self.value_id, self.work_package_id, target, self.amount, self.currency, self.evidence_ids + evidence_ids)

