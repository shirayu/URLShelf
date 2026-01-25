from __future__ import annotations

import sqlite3
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import bleach
import markdown
from flask import Flask, Response, abort, redirect, render_template, request
from werkzeug.wrappers import Response as WerkzeugResponse

ResponseReturnValue = Response | WerkzeugResponse | str

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_ROOT / "data" / "db.sqlite3"

ALLOWED_TAGS: list[str] = sorted(
    {
        *bleach.sanitizer.ALLOWED_TAGS,
        "p",
        "pre",
        "code",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "img",
        "blockquote",
        "hr",
        "br",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
}
ALLOWED_PROTOCOLS = sorted({*bleach.sanitizer.ALLOWED_PROTOCOLS, "data"})

app = Flask(__name__)
# Allow larger form payloads to avoid Werkzeug capacity errors.
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["MAX_FORM_MEMORY_SIZE"] = 50 * 1024 * 1024


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path != "/":
        return path.rstrip("/")
    return path


def normalize_route_path(path: str) -> str:
    encoded = quote(path, safe="/")
    return normalize_path("/" + encoded)


def parse_target_url(raw_url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must start with http or https")
    if not parsed.netloc:
        raise ValueError("URL host is required")
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = normalize_path(parsed.path)
    return parsed.geturl(), scheme, host, path


def sanitize_html(html_text: str) -> str:
    cleaned = bleach.clean(
        html_text,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(cleaned)


def render_markdown(md_text: str) -> str:
    rendered = markdown.markdown(md_text, extensions=["fenced_code", "tables"])
    return sanitize_html(rendered)


def derive_markdown_title(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback


def get_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                scheme TEXT NOT NULL,
                host TEXT NOT NULL,
                path TEXT NOT NULL,
                content_raw TEXT NOT NULL,
                content_type TEXT NOT NULL CHECK(content_type IN ('markdown','html')),
                content_html TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}
        if "scheme" not in columns:
            conn.execute("ALTER TABLE pages ADD COLUMN scheme TEXT NOT NULL DEFAULT 'https'")
            rows = conn.execute("SELECT id, url FROM pages").fetchall()
            for row in rows:
                try:
                    _, scheme, _, _ = parse_target_url(row["url"])
                except ValueError:
                    scheme = "https"
                conn.execute("UPDATE pages SET scheme = ? WHERE id = ?", (scheme, row["id"]))
        conn.execute("DROP INDEX IF EXISTS idx_pages_host_path")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pages_scheme_host_path ON pages(scheme, host, path)")


@app.route("/", methods=["GET"])
def index() -> ResponseReturnValue:
    with get_db(app.config["DB_PATH"]) as conn:
        rows = conn.execute(
            "SELECT url, scheme, host, path, updated_at FROM pages ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
    return render_template("index.html", rows=rows)


@app.route("/save", methods=["POST"])
def save() -> ResponseReturnValue:
    raw_url = (request.form.get("url") or "").strip()
    content = request.form.get("content") or ""
    content_type = (request.form.get("content_type") or "").strip().lower()

    if not raw_url:
        abort(400, "URL is required")
    if not content:
        abort(400, "Content is required")
    if content_type not in {"markdown", "html"}:
        abort(400, "content_type must be markdown or html")

    try:
        normalized_url, scheme, host, path = parse_target_url(raw_url)
    except ValueError as exc:
        abort(400, str(exc))

    if content_type == "markdown":
        content_html = render_markdown(content)
    else:
        content_html = sanitize_html(content)

    now = utc_now_iso()

    with get_db(app.config["DB_PATH"]) as conn:
        conn.execute(
            """
            INSERT INTO pages (url, scheme, host, path, content_raw, content_type, content_html, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scheme, host, path)
            DO UPDATE SET
                url = excluded.url,
                content_raw = excluded.content_raw,
                content_type = excluded.content_type,
                content_html = excluded.content_html,
                updated_at = excluded.updated_at
            """,
            (normalized_url, scheme, host, path, content, content_type, content_html, now, now),
        )

    view_path = path.lstrip("/")
    return redirect(f"/page/{scheme}/{host}/{view_path}")


@app.route("/page/<scheme>/<host>/", defaults={"page_path": ""}, methods=["GET"])
@app.route("/page/<scheme>/<host>/<path:page_path>", methods=["GET"])
def view_page(scheme: str, host: str, page_path: str) -> ResponseReturnValue:
    normalized_scheme = scheme.lower()
    normalized_host = host.lower()
    normalized_path = normalize_route_path(page_path)
    with get_db(app.config["DB_PATH"]) as conn:
        row = conn.execute(
            "SELECT url, content_html, content_raw, content_type FROM pages WHERE scheme = ? AND host = ? AND path = ?",
            (normalized_scheme, normalized_host, normalized_path),
        ).fetchone()
    if row is None:
        abort(404)
    if row["content_type"] == "markdown":
        title = derive_markdown_title(row["content_raw"], row["url"])
    else:
        title = row["url"]
    return render_template(
        "page.html",
        title=title,
        url=row["url"],
        content_html=row["content_html"],
    )


@app.route("/manage", methods=["GET"])
def manage_pages() -> ResponseReturnValue:
    with get_db(app.config["DB_PATH"]) as conn:
        rows = conn.execute("SELECT url, scheme, host, path, updated_at FROM pages ORDER BY updated_at DESC").fetchall()
    return render_template("manage.html", rows=rows)


@app.route("/edit/<scheme>/<host>/", defaults={"page_path": ""}, methods=["GET"])
@app.route("/edit/<scheme>/<host>/<path:page_path>", methods=["GET"])
def edit_page(scheme: str, host: str, page_path: str) -> ResponseReturnValue:
    normalized_scheme = scheme.lower()
    normalized_host = host.lower()
    normalized_path = normalize_route_path(page_path)
    with get_db(app.config["DB_PATH"]) as conn:
        row = conn.execute(
            """
            SELECT url, scheme, host, path, content_raw, content_type, updated_at
            FROM pages
            WHERE scheme = ? AND host = ? AND path = ?
            """,
            (normalized_scheme, normalized_host, normalized_path),
        ).fetchone()
    if row is None:
        abort(404)
    return render_template(
        "edit.html",
        url=row["url"],
        scheme=row["scheme"],
        host=row["host"],
        path=row["path"],
        content_raw=row["content_raw"],
        content_type=row["content_type"],
        updated_at=row["updated_at"],
    )


@app.route("/update", methods=["POST"])
def update_page() -> ResponseReturnValue:
    raw_url = (request.form.get("url") or "").strip()
    content = request.form.get("content") or ""
    content_type = (request.form.get("content_type") or "").strip().lower()
    original_scheme = (request.form.get("original_scheme") or "").strip().lower()
    original_host = (request.form.get("original_host") or "").strip().lower()
    original_path = normalize_path(request.form.get("original_path") or "")

    if not raw_url:
        abort(400, "URL is required")
    if not content:
        abort(400, "Content is required")
    if content_type not in {"markdown", "html"}:
        abort(400, "content_type must be markdown or html")
    if not original_scheme or not original_host or not original_path:
        abort(400, "Original page info is required")

    try:
        normalized_url, scheme, host, path = parse_target_url(raw_url)
    except ValueError as exc:
        abort(400, str(exc))

    if content_type == "markdown":
        content_html = render_markdown(content)
    else:
        content_html = sanitize_html(content)

    now = utc_now_iso()

    with get_db(app.config["DB_PATH"]) as conn:
        conn.execute(
            """
            INSERT INTO pages (url, scheme, host, path, content_raw, content_type, content_html, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scheme, host, path)
            DO UPDATE SET
                url = excluded.url,
                content_raw = excluded.content_raw,
                content_type = excluded.content_type,
                content_html = excluded.content_html,
                updated_at = excluded.updated_at
            """,
            (normalized_url, scheme, host, path, content, content_type, content_html, now, now),
        )
        if scheme != original_scheme or host != original_host or path != original_path:
            conn.execute(
                "DELETE FROM pages WHERE scheme = ? AND host = ? AND path = ?",
                (original_scheme, original_host, original_path),
            )

    view_path = path.lstrip("/")
    return redirect(f"/page/{scheme}/{host}/{view_path}")


@app.route("/delete/<scheme>/<host>/", defaults={"page_path": ""}, methods=["POST"])
@app.route("/delete/<scheme>/<host>/<path:page_path>", methods=["POST"])
def delete_page(scheme: str, host: str, page_path: str) -> ResponseReturnValue:
    normalized_scheme = scheme.lower()
    normalized_host = host.lower()
    normalized_path = normalize_route_path(page_path)
    with get_db(app.config["DB_PATH"]) as conn:
        conn.execute(
            "DELETE FROM pages WHERE scheme = ? AND host = ? AND path = ?",
            (normalized_scheme, normalized_host, normalized_path),
        )
    return redirect("/manage")


def parse_args() -> tuple[str, int, Path]:
    parser = ArgumentParser(description="URLShelf web app")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=9432, type=int)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    return str(args.host), int(args.port), Path(args.db_path)


def main() -> None:
    host, port, db_path = parse_args()
    app.config["DB_PATH"] = db_path
    init_db(db_path)
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
