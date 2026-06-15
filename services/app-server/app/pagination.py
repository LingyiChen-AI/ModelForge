"""Server-side pagination helper. Endpoints keep returning a plain list (response_model
unchanged); the total row count is sent in the `X-Total-Count` response header (exposed
via CORS) so the frontend can render page controls."""
from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 200


def paginate(db: Session, stmt, response: Response, page: int | None, page_size: int = 20):
    """Return the page's ORM rows and set X-Total-Count. `stmt` must already include
    ordering + any scope/filter conditions.

    Pagination is OPT-IN: when `page` is None the full list is returned (so the same
    endpoint can still feed dropdowns/selectors that need every row). When `page` is given,
    limit/offset is applied."""
    if page is None:
        rows = db.execute(stmt).scalars().all()
        response.headers["X-Total-Count"] = str(len(rows))
        return rows
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    response.headers["X-Total-Count"] = str(total)
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()


def paginate_list(rows: list, response: Response, page: int | None, page_size: int = 20) -> list:
    """Same opt-in pagination for an already-computed list (e.g. an aggregate)."""
    response.headers["X-Total-Count"] = str(len(rows))
    if page is None:
        return rows
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    start = (page - 1) * page_size
    return rows[start:start + page_size]
