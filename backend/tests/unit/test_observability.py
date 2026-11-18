import json

import sentry_sdk

from recruitai.config import Settings
from recruitai.core.logging import request_context
from recruitai.core.observability import before_send, init_sentry

EMAIL = "jane.doe@example.com"
CV = "Jane Doe, 12 rue des Lilas, led payroll migration at Acme"


def _event() -> dict:
    return {
        "event_id": "abc",
        "level": "error",
        "release": "deadbeef",
        "environment": "staging",
        "tags": {"component": "api", "secret_tag": CV},
        "user": {"email": EMAIL, "ip_address": "10.0.0.1"},
        "request": {
            "method": "POST",
            "url": f"https://api.example.com/api/v1/letters?email={EMAIL}",
            "query_string": f"email={EMAIL}",
            "data": {"cv_text": CV},
            "headers": {"Authorization": "Bearer eyJabc.def.ghi"},
            "cookies": {"session": "s3cret"},
            "env": {"REMOTE_ADDR": "10.0.0.1"},
        },
        "logentry": {"message": f"failed for {EMAIL}", "params": [CV]},
        "breadcrumbs": {"values": [{"message": CV}]},
        "extra": {"body": CV},
        "contexts": {"runtime": {"name": "CPython"}, "response": {"body": CV}},
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": f"cannot parse: {CV}",
                    "module": "builtins",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "recruitai/modules/letters/service.py",
                                "function": "generate",
                                "lineno": 42,
                                "vars": {"cv": CV, "email": EMAIL},
                            }
                        ]
                    },
                }
            ]
        },
    }


def test_before_send_keeps_type_stack_tags_and_drops_personal_data():
    with request_context(request_id="req-1"):
        out = before_send(_event(), {})

    dumped = json.dumps(out)
    for personal in (EMAIL, CV, "Lilas", "Bearer", "s3cret", "10.0.0.1", "cv_text"):
        assert personal not in dumped
    exc = out["exception"]["values"][0]
    assert exc["type"] == "ValueError" and "value" not in exc
    assert exc["stacktrace"]["frames"] == [
        {
            "filename": "recruitai/modules/letters/service.py",
            "function": "generate",
            "lineno": 42,
        }
    ]
    assert out["tags"] == {"component": "api", "request_id": "req-1"}
    assert out["release"] == "deadbeef"
    assert out["request"] == {
        "method": "POST",
        "url": "https://api.example.com/api/v1/letters",
    }


def test_empty_dsn_does_not_start_sentry():
    init_sentry(Settings.model_construct(sentry_dsn=""), "api")
    assert not sentry_sdk.get_client().is_active()
