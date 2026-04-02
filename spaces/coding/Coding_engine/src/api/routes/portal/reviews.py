"""
Cell review API endpoints.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.portal import CellRegistry, CellReview, ReviewVote, VoteType
from src.models.portal.base import get_db

router = APIRouter(prefix="/cells/{cell_id}/reviews", tags=["reviews"])


class ReviewCreate(BaseModel):
    """Schema for creating a review."""
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=20, max_length=5000)
    version: Optional[str] = None


class ReviewUpdate(BaseModel):
    """Schema for updating a review."""
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, min_length=20, max_length=5000)


class ReviewResponse(BaseModel):
    """Schema for review response."""
    id: str
    cell_id: str
    user_id: str
    user_name: str
    user_avatar_url: Optional[str]
    rating: int
    title: Optional[str]
    content: str
    cell_version: Optional[str]
    is_verified_purchase: bool
    is_edited: bool
    helpful_count: int
    not_helpful_count: int
    author_response: Optional[str]
    author_response_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Schema for review list."""
    items: List[ReviewResponse]
    total: int
    average_rating: float
    rating_distribution: dict


async def get_current_user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


async def get_current_user_name() -> str:
    return "Demo User"


@router.get("", response_model=ReviewListResponse)
async def list_reviews(
    cell_id: str,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("recent", regex="^(recent|helpful|rating_high|rating_low)$"),
):
    """List reviews for a cell."""
    # Get reviews
    query = select(CellReview).where(
        CellReview.cell_id == cell_id,
        CellReview.is_approved == True,
    )

    # Apply sorting
    if sort_by == "recent":
        query = query.order_by(CellReview.created_at.desc())
    elif sort_by == "helpful":
        query = query.order_by(CellReview.helpful_count.desc())
    elif sort_by == "rating_high":
        query = query.order_by(CellReview.rating.desc())
    elif sort_by == "rating_low":
        query = query.order_by(CellReview.rating.asc())

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(
            select(CellReview).where(
                CellReview.cell_id == cell_id,
                CellReview.is_approved == True,
            ).subquery()
        )
    )
    total = count_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    reviews = result.scalars().all()

    # Calculate rating distribution
    dist_result = await db.execute(
        select(CellReview.rating, func.count())
        .where(CellReview.cell_id == cell_id, CellReview.is_approved == True)
        .group_by(CellReview.rating)
    )
    rating_dist = {str(r): c for r, c in dist_result.all()}

    # Get average rating
    avg_result = await db.execute(
        select(func.avg(CellReview.rating))
        .where(CellReview.cell_id == cell_id, CellReview.is_approved == True)
    )
    avg_rating = avg_result.scalar() or 0.0

    return ReviewListResponse(
        items=reviews,
        total=total,
        average_rating=round(float(avg_rating), 2),
        rating_distribution=rating_dist,
    )


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    cell_id: str,
    review: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    user_name: str = Depends(get_current_user_name),
):
    """Create a review for a cell."""
    # Check cell exists
    cell_result = await db.execute(
        select(CellRegistry).where(CellRegistry.id == cell_id)
    )
    cell = cell_result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    # Check user hasn't already reviewed
    existing = await db.execute(
        select(CellReview).where(
            CellReview.cell_id == cell_id,
            CellReview.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="You have already reviewed this cell",
        )

    db_review = CellReview(
        id=str(uuid4()),
        cell_id=cell_id,
        user_id=user_id,
        user_name=user_name,
        rating=review.rating,
        title=review.title,
        content=review.content,
        cell_version=review.version,
    )

    db.add(db_review)
    await db.flush()

    # Update cell rating stats
    await _update_cell_ratings(db, cell_id)

    await db.refresh(db_review)
    return db_review


@router.patch("/{review_id}", response_model=ReviewResponse)
async def update_review(
    cell_id: str,
    review_id: str,
    review_update: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update own review."""
    result = await db.execute(
        select(CellReview).where(
            CellReview.id == review_id,
            CellReview.cell_id == cell_id,
            CellReview.user_id == user_id,
        )
    )
    db_review = result.scalar_one_or_none()

    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")

    update_data = review_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_review, field, value)

    db_review.is_edited = True
    db_review.edited_at = datetime.now(timezone.utc)

    await db.flush()

    # Update cell rating stats if rating changed
    if "rating" in update_data:
        await _update_cell_ratings(db, cell_id)

    await db.refresh(db_review)
    return db_review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    cell_id: str,
    review_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete own review."""
    result = await db.execute(
        select(CellReview).where(
            CellReview.id == review_id,
            CellReview.cell_id == cell_id,
            CellReview.user_id == user_id,
        )
    )
    db_review = result.scalar_one_or_none()

    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")

    await db.delete(db_review)
    await _update_cell_ratings(db, cell_id)


@router.post("/{review_id}/vote")
async def vote_review(
    cell_id: str,
    review_id: str,
    vote_type: VoteType,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Vote on a review's helpfulness."""
    # Check review exists
    review_result = await db.execute(
        select(CellReview).where(
            CellReview.id == review_id,
            CellReview.cell_id == cell_id,
        )
    )
    review = review_result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Check for existing vote
    existing = await db.execute(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id,
            ReviewVote.user_id == user_id,
        )
    )
    existing_vote = existing.scalar_one_or_none()

    if existing_vote:
        # Update existing vote
        old_type = existing_vote.vote_type
        existing_vote.vote_type = vote_type

        # Update counters
        if old_type != vote_type:
            if old_type == VoteType.HELPFUL:
                review.helpful_count -= 1
            else:
                review.not_helpful_count -= 1

            if vote_type == VoteType.HELPFUL:
                review.helpful_count += 1
            else:
                review.not_helpful_count += 1
    else:
        # Create new vote
        db.add(ReviewVote(
            id=str(uuid4()),
            review_id=review_id,
            user_id=user_id,
            vote_type=vote_type,
        ))

        if vote_type == VoteType.HELPFUL:
            review.helpful_count += 1
        else:
            review.not_helpful_count += 1

    await db.flush()
    return {"status": "voted", "vote_type": vote_type}


@router.delete("/{review_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vote(
    cell_id: str,
    review_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Remove vote from a review."""
    vote_result = await db.execute(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id,
            ReviewVote.user_id == user_id,
        )
    )
    vote = vote_result.scalar_one_or_none()

    if vote:
        # Update review counters
        review_result = await db.execute(
            select(CellReview).where(CellReview.id == review_id)
        )
        review = review_result.scalar_one()

        if vote.vote_type == VoteType.HELPFUL:
            review.helpful_count -= 1
        else:
            review.not_helpful_count -= 1

        await db.delete(vote)


async def _update_cell_ratings(db: AsyncSession, cell_id: str) -> None:
    """Update denormalized rating stats on cell."""
    result = await db.execute(
        select(
            func.count(CellReview.id),
            func.avg(CellReview.rating),
        )
        .where(CellReview.cell_id == cell_id, CellReview.is_approved == True)
    )
    count, avg = result.one()

    await db.execute(
        update(CellRegistry)
        .where(CellRegistry.id == cell_id)
        .values(
            rating_count=count or 0,
            average_rating=round(float(avg or 0), 2),
        )
    )
