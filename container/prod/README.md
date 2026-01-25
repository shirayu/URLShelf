# Production Container

Production-ready Docker container for URLShelf.

## Quick Start

### GitHub Container Registry (GHCR)

This repo includes a GitHub Actions workflow to build and publish (manual only):

- Trigger: GitHub Actions → **Build and Publish Container (GHCR)** → Run workflow
- Image: `ghcr.io/shirayu/urlshelf`
- Tags: `latest` (default branch), `sha`, and git tag (`v*`)

#### Make GHCR package public (recommended)

1. GitHub → your repo → Packages → `urlshelf`
2. Package settings → Visibility → **Public**

If you keep it **private**, the server must login first:

```bash
podman login ghcr.io
```

### 1. Build and Run

#### Using Podman Compose (Recommended)

```bash
# Build and start the service
podman compose -p urlshelf_prod -f container/prod/compose.yaml up -d

# View logs
podman compose -p urlshelf_prod -f container/prod/compose.yaml logs -f

# Stop the service
podman compose -p urlshelf_prod -f container/prod/compose.yaml down
```

#### Using Docker Compose

```bash
# Build and start the service
docker compose -p urlshelf_prod -f container/prod/compose.yaml up -d

# View logs
docker compose -p urlshelf_prod -f container/prod/compose.yaml logs -f

# Stop the service
docker compose -p urlshelf_prod -f container/prod/compose.yaml down
```

### 2. Access the Application

The application will be available at:

- <http://localhost:9432>

## Configuration

### Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `URLSHELF_PORT` | `9432` | Port to expose the service on |

### Data Persistence

Application data is stored in the `urlshelf-data` volume, which persists the SQLite database at `/data/db.sqlite3`.

To backup the data:

```bash
# Using Docker
docker run --rm -v urlshelf-data:/data -v $(pwd):/backup alpine tar czf /backup/urlshelf-backup.tar.gz /data

# Using Podman
podman run --rm -v urlshelf-data:/data -v $(pwd):/backup:z alpine tar czf /backup/urlshelf-backup.tar.gz /data
```

To restore from backup:

```bash
# Using Docker
docker run --rm -v urlshelf-data:/data -v $(pwd):/backup alpine tar xzf /backup/urlshelf-backup.tar.gz -C /

# Using Podman
podman run --rm -v urlshelf-data:/data -v $(pwd):/backup:z alpine tar xzf /backup/urlshelf-backup.tar.gz -C /
```

## Troubleshooting

### Check Container Status

```bash
# Using Docker
docker ps -a | grep urlshelf

# Using Podman
podman ps -a | grep urlshelf
```

### View Logs

```bash
# Using Docker
docker logs urlshelf

# Using Podman
podman logs urlshelf
```
