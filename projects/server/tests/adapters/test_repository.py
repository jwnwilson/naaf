from adapters.database.ports import PaginatedResult


def test_paginated_result_shape():
    page = PaginatedResult(results=[1, 2], total=2, page_size=50, page_number=1)
    assert page.total == 2
    assert page.results == [1, 2]
