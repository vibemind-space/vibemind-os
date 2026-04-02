"""
Cell search and discovery API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.portal import CellRegistry, CellVisibility, CellCategory
from src.models.portal.base import get_db

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class CellSearchResult(BaseModel):
    """Schema for search result item."""
    id: str
    namespace: str
    display_name: str
    short_description: Optional[str]
    category: CellCategory
    tags: List[str]
    icon_url: Optional[str]
    latest_version: Optional[str]
    average_rating: float
    rating_count: int
    download_count: int
    is_verified: bool
    is_featured: bool

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Schema for search response."""
    items: List[CellSearchResult]
    total: int
    page: int
    page_size: int
    facets: dict


class TrendingResponse(BaseModel):
    """Schema for trending cells."""
    items: List[CellSearchResult]


@router.get("/search", response_model=SearchResponse)
async def search_cells(
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = Query(None, min_length=2, max_length=100),
    category: Optional[CellCategory] = None,
    tags: Optional[List[str]] = Query(None),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    is_verified: Optional[bool] = None,
    sort_by: str = Query("relevance", regex="^(relevance|downloads|rating|recent)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Search cells in the marketplace.

    Only returns public, published cells.
    """
    # Base query for public cells
    query = select(CellRegistry).where(
        CellRegistry.visibility == CellVisibility.PUBLIC,
        CellRegistry.is_published == True,
        CellRegistry.is_deprecated == False,
    )

    # Text search
    if q:
        search_term = f"%{q}%"
        query = query.where(
            or_(
                CellRegistry.name.ilike(search_term),
                CellRegistry.display_name.ilike(search_term),
                CellRegistry.description.ilike(search_term),
                CellRegistry.namespace.ilike(search_term),
            )
        )

    # Category filter
    if category:
        query = query.where(CellRegistry.category == category)

    # Tags filter
    if tags:
        query = query.where(CellRegistry.tags.contains(tags))

    # Rating filter
    if min_rating is not None:
        query = query.where(CellRegistry.average_rating >= min_rating)

    # Verified filter
    if is_verified is not None:
        query = query.where(CellRegistry.is_verified == is_verified)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Sorting
    if sort_by == "downloads":
        query = query.order_by(CellRegistry.download_count.desc())
    elif sort_by == "rating":
        query = query.order_by(CellRegistry.average_rating.desc())
    elif sort_by == "recent":
        query = query.order_by(CellRegistry.published_at.desc())
    else:  # relevance
        if q:
            # Prioritize name matches, then downloads
            query = query.order_by(
                CellRegistry.name.ilike(f"{q}%").desc(),
                CellRegistry.download_count.desc(),
            )
        else:
            query = query.order_by(CellRegistry.download_count.desc())

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    cells = result.scalars().all()

    # Build facets
    facets = await _build_facets(db)

    return SearchResponse(
        items=cells,
        total=total,
        page=page,
        page_size=page_size,
        facets=facets,
    )


@router.get("/trending", response_model=TrendingResponse)
async def get_trending_cells(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[CellCategory] = None,
):
    """
    Get trending cells based on recent activity.
    """
    query = select(CellRegistry).where(
        CellRegistry.visibility == CellVisibility.PUBLIC,
        CellRegistry.is_published == True,
        CellRegistry.is_deprecated == False,
    )

    if category:
        query = query.where(CellRegistry.category == category)

    # Simple trending: recent downloads + high rating
    query = query.order_by(
        CellRegistry.download_count.desc(),
        CellRegistry.average_rating.desc(),
    ).limit(limit)

    result = await db.execute(query)
    cells = result.scalars().all()

    return TrendingResponse(items=cells)


@router.get("/featured", response_model=TrendingResponse)
async def get_featured_cells(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get featured cells (curated by admins).
    """
    query = select(CellRegistry).where(
        CellRegistry.visibility == CellVisibility.PUBLIC,
        CellRegistry.is_published == True,
        CellRegistry.is_featured == True,
    ).order_by(CellRegistry.download_count.desc()).limit(limit)

    result = await db.execute(query)
    cells = result.scalars().all()

    return TrendingResponse(items=cells)


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """
    List categories with cell counts.
    """
    result = await db.execute(
        select(CellRegistry.category, func.count(CellRegistry.id))
        .where(
            CellRegistry.visibility == CellVisibility.PUBLIC,
            CellRegistry.is_published == True,
        )
        .group_by(CellRegistry.category)
    )

    categories = [
        {"category": cat.value, "count": count}
        for cat, count in result.all()
    ]

    return {"categories": categories}


@router.get("/tags")
async def list_popular_tags(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List popular tags.
    """
    # This would need a more sophisticated query in production
    # For now, return a simple list
    result = await db.execute(
        select(CellRegistry.tags)
        .where(
            CellRegistry.visibility == CellVisibility.PUBLIC,
            CellRegistry.is_published == True,
        )
        .limit(100)
    )

    # Count tag occurrences
    tag_counts = {}
    for (tags,) in result.all():
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Sort by count and return top tags
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    return {
        "tags": [
            {"name": tag, "count": count}
            for tag, count in sorted_tags[:limit]
        ]
    }


async def _build_facets(db: AsyncSession) -> dict:
    """Build search facets."""
    # Category facet
    cat_result = await db.execute(
        select(CellRegistry.category, func.count())
        .where(
            CellRegistry.visibility == CellVisibility.PUBLIC,
            CellRegistry.is_published == True,
        )
        .group_by(CellRegistry.category)
    )
    category_facet = {cat.value: count for cat, count in cat_result.all()}

    # Rating facet
    rating_result = await db.execute(
        select(
            func.floor(CellRegistry.average_rating),
            func.count()
        )
        .where(
            CellRegistry.visibility == CellVisibility.PUBLIC,
            CellRegistry.is_published == True,
        )
        .group_by(func.floor(CellRegistry.average_rating))
    )
    rating_facet = {f"{int(rating)}+": count for rating, count in rating_result.all() if rating}

    return {
        "categories": category_facet,
        "ratings": rating_facet,
    }
