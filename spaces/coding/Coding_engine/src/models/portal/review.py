"""
Review and rating models for cells.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class VoteType(str, Enum):
    """Vote types for reviews."""
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class CellReview(Base, TimestampMixin):
    """
    User review of a cell.
    """
    __tablename__ = "cell_reviews"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    cell_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,  # References external auth user
    )
    cell_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Rating (1-5 stars)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    # Review content
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # User info (denormalized)
    user_name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Moderation
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    moderation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Helpfulness
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Response from author
    author_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    cell: Mapped["CellRegistry"] = relationship("CellRegistry", back_populates="reviews")
    votes: Mapped[List["ReviewVote"]] = relationship(
        "ReviewVote",
        back_populates="review",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("cell_id", "user_id", name="uq_cell_review_user"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        Index("ix_cell_reviews_cell_id", "cell_id"),
        Index("ix_cell_reviews_user_id", "user_id"),
        Index("ix_cell_reviews_rating", "rating"),
        Index("ix_cell_reviews_is_approved", "is_approved"),
        Index("ix_cell_reviews_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
    )

    def __repr__(self) -> str:
        return f"<CellReview(cell_id={self.cell_id}, user_id={self.user_id}, rating={self.rating})>"

    @property
    def helpfulness_score(self) -> float:
        """Calculate helpfulness score."""
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return 0.0
        return self.helpful_count / total


class ReviewVote(Base, TimestampMixin):
    """
    Vote on whether a review is helpful.
    """
    __tablename__ = "review_votes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    review_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cell_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
    )
    vote_type: Mapped[VoteType] = mapped_column(
        SQLEnum(VoteType),
        nullable=False,
    )

    # Relationships
    review: Mapped["CellReview"] = relationship("CellReview", back_populates="votes")

    __table_args__ = (
        UniqueConstraint("review_id", "user_id", name="uq_review_vote_user"),
        Index("ix_review_votes_review_id", "review_id"),
    )

    def __repr__(self) -> str:
        return f"<ReviewVote(review_id={self.review_id}, vote={self.vote_type})>"


# Avoid circular import
from .cell import CellRegistry
