from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app import app, init_db  # noqa: E402


def make_client(tmp_path: Path) -> Any:
    db_path = tmp_path / "test.sqlite3"
    app.config.update(DB_PATH=db_path, TESTING=True)
    init_db(db_path)
    return app.test_client()


def save_page(client: Any, url: str, content: str, content_type: str = "markdown") -> Any:
    return client.post(
        "/save",
        data={
            "url": url,
            "content": content,
            "content_type": content_type,
        },
        follow_redirects=False,
    )


def test_manage_edit_update_delete_flow(tmp_path: Path):
    client = make_client(tmp_path)

    url1 = "https://example.com/a"
    response = save_page(client, url1, "hello", "markdown")
    assert response.status_code == 302
    location = str(response.headers.get("Location", ""))
    assert location.endswith("/page/https/example.com/a")

    manage = client.get("/manage")
    assert manage.status_code == 200
    assert url1 in manage.get_data(as_text=True)

    edit = client.get("/edit/https/example.com/a")
    assert edit.status_code == 200

    url2 = "https://example.com/b"
    update = client.post(
        "/update",
        data={
            "url": url2,
            "content": "<p>updated</p>",
            "content_type": "html",
            "original_scheme": "https",
            "original_host": "example.com",
            "original_path": "/a",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    update_location = str(update.headers.get("Location", ""))
    assert update_location.endswith("/page/https/example.com/b")

    old_page = client.get("/page/https/example.com/a")
    assert old_page.status_code == 404

    new_page = client.get("/page/https/example.com/b")
    assert new_page.status_code == 200
    assert "updated" in new_page.get_data(as_text=True)

    delete = client.post("/delete/https/example.com/b", follow_redirects=False)
    assert delete.status_code == 302
    delete_location = str(delete.headers.get("Location", ""))
    assert delete_location.endswith("/manage")

    deleted_page = client.get("/page/https/example.com/b")
    assert deleted_page.status_code == 404

    manage_after = client.get("/manage")
    assert url2 not in manage_after.get_data(as_text=True)


def test_edit_and_delete_root_path(tmp_path: Path):
    client = make_client(tmp_path)

    root_url = "https://example.com/"
    response = save_page(client, root_url, "<p>root</p>", "html")
    assert response.status_code == 302
    location = str(response.headers.get("Location", ""))
    assert location.endswith("/page/https/example.com/")

    edit = client.get("/edit/https/example.com/")
    assert edit.status_code == 200

    delete = client.post("/delete/https/example.com/", follow_redirects=False)
    assert delete.status_code == 302

    deleted_page = client.get("/page/https/example.com/")
    assert deleted_page.status_code == 404


def test_scheme_distinct_pages(tmp_path: Path):
    client = make_client(tmp_path)

    http_url = "http://example.com/a"
    https_url = "https://example.com/a"

    save_http = save_page(client, http_url, "http", "markdown")
    assert save_http.status_code == 302
    save_https = save_page(client, https_url, "https", "markdown")
    assert save_https.status_code == 302

    http_page = client.get("/page/http/example.com/a")
    https_page = client.get("/page/https/example.com/a")
    assert http_page.status_code == 200
    assert https_page.status_code == 200
    assert "http" in http_page.get_data(as_text=True)
    assert "https" in https_page.get_data(as_text=True)


def test_update_changes_scheme_and_removes_old(tmp_path: Path):
    client = make_client(tmp_path)

    save_page(client, "https://example.com/shift", "old", "markdown")

    update = client.post(
        "/update",
        data={
            "url": "http://example.com/shift",
            "content": "new",
            "content_type": "markdown",
            "original_scheme": "https",
            "original_host": "example.com",
            "original_path": "/shift",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302

    old_page = client.get("/page/https/example.com/shift")
    new_page = client.get("/page/http/example.com/shift")
    assert old_page.status_code == 404
    assert new_page.status_code == 200


def test_markdown_title_uses_heading(tmp_path: Path):
    client = make_client(tmp_path)

    save_page(client, "https://example.com/title", "# Hello Title\n\nBody", "markdown")
    page = client.get("/page/https/example.com/title")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "<title>Hello Title</title>" in html


def test_invalid_payloads_return_400(tmp_path: Path):
    client = make_client(tmp_path)

    missing_url = client.post(
        "/save",
        data={"url": "", "content": "x", "content_type": "markdown"},
    )
    assert missing_url.status_code == 400

    missing_content = client.post(
        "/save",
        data={"url": "https://example.com/missing", "content": "", "content_type": "markdown"},
    )
    assert missing_content.status_code == 400

    bad_content_type = client.post(
        "/save",
        data={"url": "https://example.com/bad", "content": "x", "content_type": "text"},
    )
    assert bad_content_type.status_code == 400

    bad_url = client.post(
        "/save",
        data={"url": "ftp://example.com", "content": "x", "content_type": "markdown"},
    )
    assert bad_url.status_code == 400

    missing_original = client.post(
        "/update",
        data={
            "url": "https://example.com/update",
            "content": "x",
            "content_type": "markdown",
            "original_scheme": "",
            "original_host": "example.com",
            "original_path": "/update",
        },
    )
    assert missing_original.status_code == 400

    bad_update_url = client.post(
        "/update",
        data={
            "url": "ftp://example.com",
            "content": "x",
            "content_type": "markdown",
            "original_scheme": "https",
            "original_host": "example.com",
            "original_path": "/update",
        },
    )
    assert bad_update_url.status_code == 400


def test_common_url_variants_are_accepted(tmp_path: Path):
    client = make_client(tmp_path)

    url_with_query_fragment = "https://example.com/path/to/page?ref=home#section"
    response = save_page(client, url_with_query_fragment, "<p>ok</p>", "html")
    assert response.status_code == 302
    assert response.headers.get("Location", "").endswith("/page/https/example.com/path/to/page")

    page = client.get("/page/https/example.com/path/to/page")
    assert page.status_code == 200
    assert "ok" in page.get_data(as_text=True)


def test_url_with_port_and_subdomain(tmp_path: Path):
    client = make_client(tmp_path)

    url_with_port = "https://sub.example.com:8443/alpha/beta"
    response = save_page(client, url_with_port, "content", "markdown")
    assert response.status_code == 302
    assert response.headers.get("Location", "").endswith("/page/https/sub.example.com:8443/alpha/beta")

    page = client.get("/page/https/sub.example.com:8443/alpha/beta")
    assert page.status_code == 200


def test_url_with_encoded_path(tmp_path: Path):
    client = make_client(tmp_path)

    url = "https://example.com/a%20b/c"
    response = save_page(client, url, "encoded", "markdown")
    assert response.status_code == 302
    assert response.headers.get("Location", "").endswith("/page/https/example.com/a%20b/c")

    page = client.get("/page/https/example.com/a%20b/c")
    assert page.status_code == 200


def test_html_is_sanitized_on_save(tmp_path: Path):
    client = make_client(tmp_path)

    html_payload = "<p>ok</p><script>alert(1)</script><img src=x onerror=alert(1)>"
    response = save_page(client, "https://example.com/sanitize", html_payload, "html")
    assert response.status_code == 302

    page = client.get("/page/https/example.com/sanitize")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "<script" not in body
    assert "onerror" not in body


def test_markdown_is_sanitized_on_save(tmp_path: Path):
    client = make_client(tmp_path)

    md_payload = "# Title\n\n<img src=x onerror=alert(1)>\n\n<script>alert(1)</script>"
    response = save_page(client, "https://example.com/sanitize-md", md_payload, "markdown")
    assert response.status_code == 302

    page = client.get("/page/https/example.com/sanitize-md")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "<script" not in body
    assert "onerror" not in body


def test_delete_nonexistent_page_redirects(tmp_path: Path):
    client = make_client(tmp_path)

    delete = client.post("/delete/https/example.com/missing", follow_redirects=False)
    assert delete.status_code == 302
    assert delete.headers.get("Location", "").endswith("/manage")
