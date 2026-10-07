"""POST/GET /api/v1/documents (P1-10), through real HTTP."""

import httpx

PDF_BYTES = b"%PDF-1.4\n%fake-pdf-for-tests"


async def test_upload_pdf_and_read_it_back(client: httpx.AsyncClient, emulator_token):
    token = emulator_token("uid-doc-1", "doc1@example.test")
    headers = {"Authorization": f"Bearer {token}"}

    upload_resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        data={"kind": "cv"},
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
    )
    assert upload_resp.status_code == 200
    document_id = upload_resp.json()["document_id"]

    read_resp = await client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert read_resp.status_code == 200
    body = read_resp.json()
    assert body["kind"] == "cv"
    assert body["mime"] == "application/pdf"
    assert body["size"] == len(PDF_BYTES)

    download = await client.get(body["download_url"])
    assert download.status_code == 200
    assert download.content == PDF_BYTES


async def test_oversized_upload_is_422(client: httpx.AsyncClient, emulator_token):
    token = emulator_token("uid-doc-2", "doc2@example.test")
    oversized = PDF_BYTES + b"0" * (10 * 1024 * 1024)

    resp = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "cv"},
        files={"file": ("cv.pdf", oversized, "application/pdf")},
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_failed"


async def test_docx_is_rejected_by_content_not_extension(
    client: httpx.AsyncClient, emulator_token
):
    token = emulator_token("uid-doc-3", "doc3@example.test")
    docx_bytes = b"PK\x03\x04" + b"\x00" * 16  # a real .docx is a zip archive

    resp = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "cv"},
        files={"file": ("cv.docx", docx_bytes, "application/octet-stream")},
    )

    assert resp.status_code == 422


async def test_cross_tenant_cannot_read_by_id_or_get_a_signed_url(
    client: httpx.AsyncClient, two_tenant_tokens
):
    """The signed URL itself has no per-tenant check (same as GCS: whoever holds the link
    can use it). What must be, and is, org-scoped is the endpoint that *hands one out* —
    org B's GET never returns org A's document, so org B never obtains a usable URL."""
    token_a, token_b = two_tenant_tokens

    upload_resp = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"kind": "cv"},
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
    )
    document_id = upload_resp.json()["document_id"]

    resp = await client.get(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert resp.status_code == 404
