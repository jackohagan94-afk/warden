# Warden

Unified all-in-one service combining [Warden](https://github.com/JudoChinX/warden) (automated media searches) and [Killarr](https://github.com/JudoChinX/killarr) (stalled download cleanup) into a single Docker container.

## Quick Start

```bash
docker compose up -d
```

## Modes

- `WARDEN_MODE=both` — Run both search and cleanup (default)
- `WARDEN_MODE=search` — Run only search (Warden)
- `WARDEN_MODE=cleanup` — Run only cleanup (Killarr)

## Configuration

See `config.example.yaml` for a complete reference. Copy it to `config.yaml` and customize.

### Instances

Define your *Arr instances under `instances:`. Each instance shares the same configuration structure:

```yaml
instances:
  sonarr-tv:
    type: sonarr
    host: "http://sonarr-tv:8989"
    api_key: "${SONARR_TV_API_KEY}"
    enabled: true
```

Supported types: `sonarr`, `radarr`, `lidarr`.

### Search Type

Control the granularity of search commands per instance:

| Type | `search_type` values | Default | API Command |
|------|---------------------|---------|-------------|
| Sonarr | `series`, `episode` | `episode` | `SeriesSearch` / `EpisodeSearch` |
| Lidarr | `artist`, `album` | `album` | `ArtistSearch` / `AlbumSearch` |
| Radarr | `movie`, `collection` | `movie` | `MoviesSearch` / `CollectionSearch` |

```yaml
instances:
  sonarr-tv:
    type: sonarr
    search_type: series        # Search entire series instead of individual episodes
  lidarr:
    type: lidarr
    search_type: artist        # Search entire artist instead of individual albums
```

**Note:** `series` search uses `SeriesSearch` with `seriesId`, which is more efficient than triggering individual episode searches.

### Collection Search (Radarr)

Radarr supports grouping movies by collection:

```yaml
global:
  radarr_collection_search_mode: "off"  # off | detect | force
```

- `off` — Standard movie-level search (default)
- `detect` — Group movies by collection when found in wanted endpoints
- `force` — Fetch from `/api/v3/collection` and search all monitored collections with missing movies

### Cleanup Caps

Limit how many items each instance can remove per cleanup cycle:

```yaml
killarr:
  max_removals_per_instance: 25   # Global default; 0 = no cap

instances:
  lidarr:
    type: lidarr
    max_removals_per_instance: 5   # Override for this instance only
```

### Season Packs (Sonarr)

Control when to search for entire seasons instead of individual episodes:

```yaml
instances:
  sonarr-tv:
    type: sonarr
    season_packs: true              # Always use season search
    # season_packs: 0.75           # Or: threshold ratio (75% of episodes missing)
    # season_packs: 5              # Or: minimum episode count
```

### Protect Downloading Series (Sonarr)

Prevent cleanup from disrupting series with active downloads:

```yaml
instances:
  sonarr-tv:
    type: sonarr
    protect_downloading_series: true
```

### Cleanup Search Scope

Control what ID is used when triggering replacement searches after cleanup:

```yaml
instances:
  sonarr-tv:
    type: sonarr
    cleanup_search_scope: series   # episode | season | series
```

- `episode` — Uses episode ID (default)
- `season` — Uses `season:seriesId:seasonNumber` format
- `series` — Uses `series:seriesId` format

When `search_type: series` is enabled, cleanup automatically uses series ID regardless of scope.

### Retry Intervals

```yaml
global:
  retry_interval_days: 5            # Default for both missing and upgrade
  retry_interval_days_missing: 3    # Override for missing items only
  retry_interval_days_upgrade: 7    # Override for upgrade items only
```

### Circuit Breaker

Skip instances after consecutive failures:

```yaml
global:
  circuit_breaker_threshold: 3      # Fetch failures
killarr:
  circuit_breaker_threshold: 3      # Cleanup failures
```

### Active Hours

Restrict operations to specific hours (UTC):

```yaml
global:
  active_hours_start: 1             # 1 AM UTC
  active_hours_end: 6               # 6 AM UTC
```

Set to `0` and `0` for all hours (default).

## Docker Compose

```yaml
services:
  warden:
    image: warden:latest
    container_name: warden
    restart: unless-stopped
    env_file:
      - .env
    environment:
      TZ: Australia/Brisbane
      LOG_LEVEL: INFO
      WARDEN_MODE: both
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    networks:
      - homelab
```

## Building

```bash
docker build -t warden:latest .
```

## License

MIT
