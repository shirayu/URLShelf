# URLShelf

URLShelf is a minimal web app that saves a URL plus Markdown/HTML content and serves it at `/page/<host>/<path>` as HTML.

## Run

```bash
task serve
```

Custom host/port:

```bash
task serve HOST=127.0.0.1 PORT=9432
```

Custom DB path:

```bash
task serve DB_PATH=./data/db.sqlite3
```

Then open the host/port you configured to use the save form.

## Save & View

1. Enter a URL and content (Markdown or HTML) and save.
2. View the rendered page at `/page/<host>/<path>`.

Example (assuming default host/port):

- Input URL: `https://forbesjapan.com/articles/detail/90132`
- View URL: `http://localhost:9432/page/forbesjapan.com/articles/detail/90132`

## Tasks

- Install deps: `task install`
- Format: `task format`
- Lint: `task lint`
- Run: `task serve`

## Notes

- SQLite DB file: `./data/db.sqlite3` by default (configurable via `--db-path` or `DB_PATH`).
- Markdown is converted to HTML and sanitized before rendering.

## License

AGPL-3.0 license
