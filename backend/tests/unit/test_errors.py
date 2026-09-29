import pytest

from recruitai.core.errors import (
    AppError,
    Forbidden,
    NotFound,
    UpstreamUnavailable,
    ValidationFailed,
)


@pytest.mark.parametrize(
    ("cls", "status", "code"),
    [
        (NotFound, 404, "not_found"),
        (Forbidden, 403, "forbidden"),
        (ValidationFailed, 422, "validation_failed"),
        (UpstreamUnavailable, 503, "upstream_unavailable"),
        (AppError, 500, "internal_error"),
    ],
)
def test_each_error_has_a_stable_status_and_code(cls, status, code):
    err = cls()

    assert (int(err.status_code), err.code) == (status, code)
    assert err.detail  # every error has a safe default message
    assert isinstance(err, AppError) and isinstance(err, Exception)


def test_detail_is_the_authored_message():
    assert NotFound("Document not found").detail == "Document not found"


def test_a_domain_specific_code_can_replace_the_default():
    err = NotFound(code="document_not_found")

    assert err.code == "document_not_found"
    assert NotFound.code == "not_found"  # the class default is untouched


@pytest.mark.parametrize(
    "bad", ["", "Not-Found", "not found", "NotFound", "1abc", "a.b"]
)
def test_codes_must_be_snake_case(bad):
    with pytest.raises(ValueError):
        NotFound(code=bad)


def test_validation_errors_carry_field_level_items():
    err = ValidationFailed(errors=[{"loc": "body.email", "type": "value_error"}])

    assert err.errors == [{"loc": "body.email", "type": "value_error"}]


def test_upstream_unavailable_can_advertise_retry_after():
    assert UpstreamUnavailable(retry_after_s=30).headers == {"Retry-After": "30"}
    assert UpstreamUnavailable().headers == {}


def test_error_message_is_available_via_str():
    assert str(Forbidden("nope")) == "nope"
