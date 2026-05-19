"""Warden unified entry point.

Supports three operational modes via WARDEN_MODE env var:
- warden: run both vigilance (search) and defence (cleanup) (default)
- vigilance: run only search (Warden)
- defence: run only cleanup (Killarr)

Legacy mode values are also accepted: both, search, cleanup.
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path

from warden.clients.arr import _CLIENT_MAP
from warden.clients.arr import ArrClient
from warden.clients.arr import CircuitBreaker
from warden.cleaner import run_cleaner_loop
from warden.config import CLEANUP_SETTINGS_SCHEMA
from warden.config import SEARCH_SETTINGS_SCHEMA
from warden.config import load_config
from warden.searcher import run_searcher_loop

if "TZ" not in os.environ:
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
logging.Formatter.converter = time.localtime
logger = logging.getLogger(__name__)

_MAX_CONNECTION_ATTEMPTS: int = 3
_RETRY_DELAY_SECONDS: int = 10

_MODE_MAP = {
    "warden": "both",
    "vigilance": "search",
    "defence": "cleanup",
    "both": "both",
    "search": "search",
    "cleanup": "cleanup",
}


def _load_config_from_paths(config_paths: list[str]) -> dict | None:
    config = None
    error_message = None
    for config_path in config_paths:
        if Path(config_path).is_file():
            try:
                config = load_config(config_path)
                logger.info(f"Loaded configuration from: {config_path}")
                error_message = None
                break
            except ValueError as error:
                error_message = f"Configuration error in {config_path}: {error}"
                break
            except FileNotFoundError:
                continue

    if error_message:
        logger.error(error_message)
    elif config is None:
        logger.error(
            "No config.yaml found. Copy config.example.yaml to config.yaml and fill in your instance details."
        )
    return config


def build_arr_clients(
    instances_config: dict,
    search_settings: dict,
    cleanup_settings: dict,
    circuit_breaker: CircuitBreaker,
    client_registry: dict[str, type[ArrClient]] | None = None,
) -> list[ArrClient]:
    registry = client_registry if client_registry is not None else _CLIENT_MAP
    clients: list[ArrClient] = []
    search_instance_keys = set(SEARCH_SETTINGS_SCHEMA)
    cleanup_instance_keys = set(CLEANUP_SETTINGS_SCHEMA)
    for arr_type, client_class in registry.items():
        for instance in instances_config.get(arr_type, []):
            search_overrides = {key: instance[key] for key in search_instance_keys if key in instance}
            cleanup_overrides = {key: instance[key] for key in cleanup_instance_keys if key in instance}
            client_search_settings = {**search_settings, **search_overrides}
            client_cleanup_settings = {**cleanup_settings, **cleanup_overrides}
            client = client_class(
                name=instance["name"],
                url=instance["url"],
                api_key=instance["api_key"],
                search_settings=client_search_settings,
                cleanup_settings=client_cleanup_settings,
                weight=instance.get("weight", 1.0),
                circuit_breaker=circuit_breaker,
            )
            clients.append(client)
            logger.info(f"Registered {arr_type.capitalize()} instance: {instance['name']} (Weight: {client.weight})")
    return clients


def verify_arr_clients(clients: list[ArrClient]) -> list[ArrClient]:
    verified: list[ArrClient] = []
    for client in clients:
        connected = False
        for attempt in range(1, _MAX_CONNECTION_ATTEMPTS + 1):
            if client.check_connection():
                if attempt > 1:
                    logger.info(f"[{client.name}] Connected on attempt {attempt}/{_MAX_CONNECTION_ATTEMPTS}.")
                connected = True
                break
            if attempt < _MAX_CONNECTION_ATTEMPTS:
                logger.warning(
                    f"[{client.name}] Connection attempt {attempt}/{_MAX_CONNECTION_ATTEMPTS} failed. "
                    f"Retrying in {_RETRY_DELAY_SECONDS}s..."
                )
                time.sleep(_RETRY_DELAY_SECONDS)
            else:
                logger.error(
                    f"[{client.name}] Could not connect after {_MAX_CONNECTION_ATTEMPTS} attempts. Skipping instance."
                )
        if connected:
            verified.append(client)
    return verified


def run() -> None:
    config = _load_config_from_paths(["config/config.yaml", "config.yaml"])
    if not config:
        sys.exit(1)

    search_settings = config.get("search_settings", {})
    cleanup_settings = config.get("cleanup_settings", {})
    instances = config.get("instances", {})

    circuit_breaker = CircuitBreaker(
        max(
            search_settings.get("circuit_breaker_threshold", 0),
            cleanup_settings.get("circuit_breaker_threshold", 0),
        )
    )

    built_clients = build_arr_clients(instances, search_settings, cleanup_settings, circuit_breaker)

    if not built_clients:
        logger.warning("No *arr instances are configured. Add at least one entry under 'instances' to begin.")
        sys.exit(1)

    active_clients = verify_arr_clients(built_clients)
    if not active_clients:
        logger.error("All configured *arr instances failed to connect. Check network connectivity and instance URLs.")
        sys.exit(1)

    raw_mode = os.environ.get("WARDEN_MODE", "warden").lower()
    mode = _MODE_MAP.get(raw_mode)
    if mode is None:
        logger.warning(f"Unrecognized WARDEN_MODE '{raw_mode}'. Defaulting to 'warden'.")
        mode = "both"

    if mode == "search":
        logger.info("Running in Vigilance mode (search only).")
        run_searcher_loop(active_clients, search_settings)
    elif mode == "cleanup":
        logger.info("Running in Defence mode (cleanup only).")
        run_cleaner_loop(active_clients, cleanup_settings)
    else:
        logger.info("Running in Warden mode (Vigilance + Defence).")
        searcher_thread = threading.Thread(
            target=run_searcher_loop, args=(active_clients, search_settings), daemon=True, name="vigilance"
        )
        cleaner_thread = threading.Thread(
            target=run_cleaner_loop, args=(active_clients, cleanup_settings), daemon=True, name="defence"
        )
        searcher_thread.start()
        cleaner_thread.start()
        try:
            searcher_thread.join()
            cleaner_thread.join()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            sys.exit(0)


if __name__ == "__main__":
    run()
