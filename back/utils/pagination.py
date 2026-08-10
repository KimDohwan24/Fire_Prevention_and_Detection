"""페이징 공통 처리 (명세서 '페이징 공통 형식' 구현)."""
import math

from flask import request


def get_page_params(default_size: int = 20, max_size: int = 100) -> tuple[int, int]:
    """쿼리스트링에서 page(1부터), size 를 읽는다."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(max_size, max(1, int(request.args.get("size", default_size))))
    except ValueError:
        page, size = 1, default_size
    return page, size


def paged_response(items: list, page: int, size: int, total_count: int) -> dict:
    return {
        "items": items,
        "page": page,
        "size": size,
        "total_count": total_count,
        "total_pages": math.ceil(total_count / size) if total_count else 0,
    }
