# Rangarr-AIO Hardening And Feature Design

Date: 2026-05-17

## Context

Rangarr-AIO combines search scheduling and stalled download cleanup for Radarr, Sonarr, and Lidarr. The current live deployment runs in `both` mode with four instances. Live configuration confirms Sonarr instances use `search_type: series`, Lidarr uses `search_type: artist`, and Radarr uses the default movie search path.

The immediate production issue was a cleanup crash after a Sonarr blocklist removal. `execute_removal()` called a nonexistent `_trigger_search()` method after deleting a queue item. The current repo now has a targeted regression test and a minimal fix that routes cleanup-triggered searches through the existing `_trigger_single()` path.

This design covers the next scoped pass: improve throughput, reduce hammering/thundering behavior, improve cleanup/search reliability, and add narrowly scoped features that fit the existing project.

## Goals

- Keep search and cleanup worker loops alive after per-instance or per-item failures.
- Reduce unnecessary API pressure against Radarr, Sonarr, Lidarr, and download clients.
- Preserve the current single-container, YAML-configured service model.
- Improve logs so each cycle explains what happened, how long it took, and what will happen next.
- Keep search modes explicit: Lidarr artist search, Sonarr series-aware search, Radarr movie search with optional collection support if safely detectable.
- Improve stalled download classification and cleanup behavior for sample-related failures.

## Non-Goals

- No web UI, database, queue broker, or external state store.
- No broad rewrite to async I/O.
- No uncontrolled parallel searches or removals.
- No guaranteed Radarr collection search until command support is verified against a running Radarr instance.
- No automatic config migration beyond accepting new optional settings with safe defaults.
- No automatic discovery/import-list management in the hardening pass. Discovery will be researched as a follow-up because it touches external Trakt credentials, Radarr/Sonarr add semantics, root folders, quality profiles, exclusions, and duplicate prevention.

## Current Search Behavior

Lidarr currently supports `search_type: artist`. In artist mode, missing and upgrade records are grouped by artist and trigger `ArtistSearch` with `artistId`. This is already enabled in the live config.

Sonarr currently supports `search_type: series`. In series mode, `season_packs` is forced on and the client groups episodes by `(seriesId, seasonNumber)`. It triggers `SeasonSearch` when a full-season search is suitable. It still falls back to `EpisodeSearch` for single episodes when the season is still airing or the season-pack threshold is not met.

Radarr currently uses `MoviesSearch` with `movieIds`. Radarr collection endpoints exist in the official OpenAPI (`/api/v3/collection` and `/api/v3/collection/{id}`), but the OpenAPI does not enumerate command names and does not prove `CollectionSearch` support. Collection search will therefore be treated as experimental and runtime-gated.

## Proposed Configuration Additions

All new settings default to current behavior unless explicitly enabled.

- `global.api_request_interval_seconds`: minimum delay between API-changing actions per instance. Default: `0` for compatibility, recommended live value: `2`.
- `global.search_after_cleanup`: whether cleanup actions should trigger a replacement search after successful removal. Default: `true` to preserve current behavior.
- `global.search_after_cleanup_actions`: cleanup actions that trigger replacement searches. Default: `['retry', 'blocklist']`.
- `global.search_jitter_seconds`: random extra delay added before search commands. Default: `0`, recommended live value: `1-5`.
- Per-instance `search_type: collection` for Radarr instances. Default remains movie search when unset.
- `global.radarr_collection_search_mode`: `off`, `detect`, or `force`. Default: `off`. Collection searches require both a Radarr instance with `search_type: collection` and this mode set to `detect` or `force`.
- `killarr.cleanup_page_size`: page size for queue scans. Default: `100`.
- `killarr.max_cleanup_queue_records`: maximum queue records to fetch per cleanup cycle. Default: `0` meaning unlimited.
- `killarr.delete_timeout_seconds`: timeout for queue deletion calls. Default: `15`.
- `killarr.max_removals_per_instance`: optional per-instance cleanup cap inside a cycle. Default: `0` meaning use global batch allocation only.
- `killarr.search_after_cleanup`: cleanup-specific override of the global setting. Default: unset.

## Reliability Design

Search and cleanup cycles should isolate failures by client and by item. A failing client fetch should log an error, update the circuit breaker, and allow other clients to continue. A failed queue deletion or search command should not kill the worker thread. The outer searcher and cleaner loops should catch unexpected cycle-level exceptions, log them with stack traces, sleep until the next interval, and continue.

This addresses both the observed cleaner thread crash and future single-item failures. It also makes circuit breaker behavior meaningful because the loop remains alive long enough to recover.

## Anti-Hammering Design

Rangarr-AIO should pace mutating API calls. Search commands and cleanup-triggered follow-up searches should pass through a per-client rate limiter. The limiter should use monotonic time and apply a configured minimum interval plus optional jitter. It should apply only to mutating calls (`POST /command`, `DELETE /queue/{id}`), not all read calls, because read calls already run once per cycle and have batch/page controls.

The existing stagger settings remain useful for global batch pacing. The new per-client limiter prevents bursts when multiple code paths issue commands close together, especially after cleanup removes several stalled items and immediately searches replacements.

## Search Efficiency Design

Sonarr series search should remain enabled. The efficiency pass should focus on avoiding repeated metadata fetches and preserving episode fallback behavior:

- Fetch season metadata once per Sonarr cycle when season mode is active.
- Reuse the same metadata for missing and upgrade calculations in that cycle.
- Keep fallback to `EpisodeSearch` for airing seasons and seasons below threshold.
- Avoid custom-format upgrade scans when `upgrade_batch_size` is `0`.
- Log how many season searches and episode searches were selected.

Lidarr artist search should stay enabled. The current artist grouping is in scope to keep, but not to broaden into per-track logic.

Radarr collection search should be introduced only if runtime detection confirms the command is supported. Detection can post a dry validation only if Radarr exposes enough command metadata, or it can be implemented as a conservative opt-in `force` mode for users who know their Radarr supports it. If unsupported or failing with a 400-style response, Rangarr-AIO should log once and fall back to movie search.

## Cleanup Design

Cleanup should handle blocklist plus replacement search cleanly:

- Successful `remove`, `retry`, and `blocklist` actions record cleanup cooldown state.
- Only actions in `search_after_cleanup_actions` trigger a replacement search.
- Replacement search uses the same client-specific search primitive as normal search, so Sonarr can issue `EpisodeSearch` or `SeasonSearch` according to the item identifier available.
- If replacement search fails, the removal stays successful and the error is logged without re-raising.

The classifier already maps `unable to determine if file is a sample` into `manual_import`. That behavior should be preserved and covered by tests. The wording should be documented in the sample-related test names so future changes do not regress it.

## Observability Design

Each cycle should log a compact summary:

- Cycle type: search or cleanup.
- Duration in seconds.
- Per-instance counts: fetched, evaluated, skipped, selected, removed, searched, failed.
- Search mix: missing, upgrade, movie, collection, season, episode, artist.
- Throttling: configured delay, actual sleep count, and next run time.

Logs should stay plain text and remain suitable for Docker logs. No metrics endpoint is included in this pass.

## Testing Plan

Add tests for:

- Cleanup blocklist removal triggers replacement search without calling missing methods.
- Per-item cleanup exceptions do not abort the whole removal cycle.
- Search cycle continues when one client fails and another succeeds.
- Queue pagination respects `cleanup_page_size` and `max_cleanup_queue_records`.
- Sample-related message `unable to determine if file is a sample` classifies as `manual_import`.
- Sonarr series mode can produce both season-pack searches and episode fallback searches.
- Rate limiter sleeps between mutating calls when configured and does not sleep when disabled.
- Radarr collection mode falls back to movie search when command support is not available.

## Rollout Plan

Implement this as a small sequence of changes: finish the crash fix, add failure isolation, add config defaults, add rate limiting, add queue fetch caps, improve logs, then add experimental Radarr collection detection. After tests pass, rebuild the Docker image, restart `rangarr-aio`, and watch at least one cleanup cycle and one search cycle in live logs.

## Residual Risks

Radarr collection search remains uncertain until verified against the live Radarr API. The design prevents unsupported collection search from breaking normal movie search, but it cannot promise collection behavior without runtime evidence.

Per-client throttling reduces hammering but may extend total cycle duration. This is acceptable because the service already uses staggered automation and should prefer stable API behavior over speed.

## Discovery Follow-Up

Trakt-style discovery fits the project direction, but it should not be bundled into the reliability pass as an automatic add feature. Radarr and Sonarr expose native ImportList APIs, and Trakt exposes public and authenticated list-style endpoints such as trending, popular, anticipated, watched, collected, and user lists. That gives two viable future approaches: let Rangarr-AIO manage native Arr import lists, or let Rangarr-AIO produce a dry-run recommendation feed from Trakt that a later task can add to Arr instances.

The recommended next step is a discovery research spike after hardening lands. It should verify live Radarr/Sonarr import-list schemas, required fields for Trakt lists, add/search behavior, exclusion behavior, and how to prevent request floods. Until that is known, discovery should remain disabled and should not add movies or shows automatically.
