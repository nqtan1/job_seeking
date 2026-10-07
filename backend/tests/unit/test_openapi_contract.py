"""The OpenAPI document is the contract the frontend client is generated from (`pnpm gen:api`):
every authenticated operation must document its 401, and every operation that looks a thing up
by id must document its 404, so the generated client types the error cases."""

from recruitai.main import create_app

PUBLIC = {"/health", "/ready"}


def test_every_authenticated_operation_documents_401_and_id_lookups_document_404():
    paths = create_app().openapi()["paths"]
    missing_401, missing_404 = [], []
    for path, operations in paths.items():
        if path in PUBLIC or path.startswith("/_dev"):
            continue
        for method, op in operations.items():
            codes = set(op["responses"])
            if "401" not in codes:
                missing_401.append(f"{method.upper()} {path}")
            if "{" in path and "404" not in codes:  # looks something up by id
                missing_404.append(f"{method.upper()} {path}")
    assert missing_401 == []
    assert missing_404 == []


async def test_require_role_lets_a_matching_role_through_and_forbids_the_rest():
    from uuid import uuid4

    import pytest

    from recruitai.core.errors import Forbidden
    from recruitai.core.tenancy import OrgContext, require_role

    check = require_role("owner", "recruiter")
    owner = OrgContext(org_id=uuid4(), user_id=uuid4(), role="owner")
    member = OrgContext(org_id=uuid4(), user_id=uuid4(), role="member")
    assert await check(owner) is owner
    with pytest.raises(Forbidden):
        await check(member)


def _dependency_calls(dependant) -> set:
    calls = {dependant.call}
    for sub in dependant.dependencies:
        calls |= _dependency_calls(sub)
    return calls


def test_every_api_route_requires_authentication():
    """A new endpoint cannot ship unauthenticated by accident: each /api/v1 route's dependency
    tree must reach the Firebase token check (directly or through the org context)."""
    from fastapi.routing import APIRoute

    from recruitai.core.auth import get_current_user, get_current_user_strict

    app = create_app()
    unprotected = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1"):
            calls = _dependency_calls(route.dependant)
            if not ({get_current_user, get_current_user_strict} & calls):
                unprotected.append(f"{sorted(route.methods)} {route.path}")
    assert unprotected == []
    assert (
        sum(
            isinstance(r, APIRoute) and r.path.startswith("/api/v1") for r in app.routes
        )
        >= 30  # the loop is not vacuous
    )
