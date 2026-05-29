# Decypharr extras (optional)

Host-side helper scripts for running Warden alongside
[decypharr](https://github.com/sirrobot01/decypharr) and its FUSE/DFS mount on
Unraid. **Entirely optional** — if you do not use decypharr, ignore this folder.
They run on the host (not inside the Warden container) because they need
`docker` and `fusermount`, which a least-privilege *Arr container should not have.

| Script | What it does | How to run |
|--------|--------------|------------|
| `heartbeat.sh` | Detects a stale/hung decypharr FUSE mount and auto-recovers it (`fusermount -uz` + `docker restart`), with startup-grace, cooldown, and loop-guard. Optional opt-in arr-pause during recovery. | `sh enable.sh` (cron every 3 min) |
| `janitor.sh` | Clean Unraid array-stop: sync, stop DB + decypharr, lazy-unmount the FUSE mount so the array is not left busy. ZFS export off by default. | Unraid &rarr; User Scripts &rarr; schedule **"At Stopping of Array"** |

## Why these exist

Decypharr serves media via a FUSE mount. If it crashes, the mount goes stale
("Transport endpoint is not connected") and the library reads as broken until a
manual unmount + restart. Decypharr only self-heals the mount **at startup**, so
a running container whose mount died stays broken. `heartbeat.sh` closes that gap.
`janitor.sh` makes sure a clean array stop releases the mount first.

## Enable / disable

```sh
sh enable.sh            # install heartbeat (cron, every 3 min)
sh enable.sh --disable  # remove it
```

Add `janitor.sh` separately via Unraid User Scripts ("At Stopping of Array").

## Configure

Edit the CONFIG block at the top of each script:

- `MOUNT` / `FUSE_MOUNTS` — your decypharr mount path (default `/mnt/cache/data/dfs`)
- `CONTAINER` / `STOP_CONTAINERS` — decypharr container name
- `PAUSE_ARRS=Y` (heartbeat) — pause the *Arrs during recovery so they do not
  flag the library as missing (off by default)
- `ZFS_POOLS` (janitor) — leave empty on a stock Unraid array

## Note on broken symlinks / re-search

Decypharr already has a built-in repair service that probes broken entries and
asks the *Arrs to delete + re-search. Enable it in the decypharr config
(`repair.enabled` + `repair.auto_repair` + a `schedule`) rather than scripting it
here. These extras only cover the mount lifecycle, which decypharr cannot fix
from inside its own crashed container.
