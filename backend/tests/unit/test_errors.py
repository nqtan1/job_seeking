import pytest

from recruitai.core.errors import (
    AppError,
    Forbidden,
    NotFound,
    UpstreamUnavailable,
    ValidationFailed,
)


def test_each_error_has_a_stable_status_code_and_authored_detail():
    expected = [
        (NotFound, 404, "not_found"),
        (Forbidden, 403, "forbidden"),
        (ValidationFailed, 422, "validation_failed"),
        (UpstreamUnavailable, 503, "upstream_unavailable"),
        (AppError, 500, "internal_error"),
    ]
    for cls, status, code in expected:
        err = cls()
        assert (int(err.status_code), err.code) == (status, code), cls.__name__
        assert err.detail and isinstance(err, AppError) and isinstance(err, Exception)

    assert (
        NotFound("Document not found").detail
        == "Document not found"
        == str(NotFound("Document not found"))
    )
    assert NotFound(code="document_not_found").code == "document_not_found"
    assert NotFound.code == "not_found"  # the class default is untouched


def test_codes_must_be_snake_case():
    for bad in ("", "Not-Found", "not found", "NotFound", "1abc", "a.b"):
        with pytest.raises(ValueError):
            NotFound(code=bad)


def test_field_errors_and_retry_after_are_carried():
    err = ValidationFailed(errors=[{"loc": "body.email", "type": "value_error"}])
    assert err.errors == [{"loc": "body.email", "type": "value_error"}]
    assert UpstreamUnavailable(retry_after_s=30).headers == {"Retry-After": "30"}
    assert UpstreamUnavailable().headers == {}
