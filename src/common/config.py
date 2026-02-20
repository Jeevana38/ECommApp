from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

@dataclass(frozen=True)
class BackendCustomerDBConfig:
    host: str
    port: int
    seller_port: int

@dataclass(frozen=True)
class EndpointConfig:
    host: str
    port: int


@dataclass(frozen=True)
class StorageConfig:
    data_dir: Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str


@dataclass(frozen=True)
class SessionConfig:
    timeout_seconds: int


@dataclass(frozen=True)
class FeatureConfig:
    enable_make_purchase: bool


@dataclass(frozen=True)
class AppConfig:
    frontend_buyer: EndpointConfig
    frontend_seller: EndpointConfig
    backend_customer_db: BackendCustomerDBConfig
    backend_product_db: EndpointConfig
    soap: EndpointConfig
    session: SessionConfig
    features: FeatureConfig
    storage: StorageConfig
    logging: LoggingConfig


def _endpoint(raw: Dict[str, Any], key: str, default_port: int) -> EndpointConfig:
    d = raw.get(key, {}) or {}
    return EndpointConfig(host=str(d.get("host", "127.0.0.1")), port=int(d.get("port", default_port)))


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    raw: Dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    session_raw = raw.get("session", {}) or {}
    features_raw = raw.get("features", {}) or {}
    storage_raw = raw.get("storage", {}) or {}
    logging_raw = raw.get("logging", {}) or {}

    return AppConfig(
        frontend_buyer=_endpoint(raw, "frontend_buyer", 8090),
        frontend_seller=_endpoint(raw, "frontend_seller", 8080),
        backend_customer_db=BackendCustomerDBConfig(
            host=str(raw.get("backend_customer_db", {}).get("host", "127.0.0.1")),
            port=int(raw.get("backend_customer_db", {}).get("port", 50051)),
            seller_port=int(raw.get("backend_customer_db", {}).get("seller_port", 50053)),
        ),
        backend_product_db=_endpoint(raw, "backend_product_db", 50052),
        soap=_endpoint(raw, "soap", 8000),
        session=SessionConfig(timeout_seconds=int(session_raw.get("timeout_seconds", 300))),
        features=FeatureConfig(enable_make_purchase=bool(features_raw.get("enable_make_purchase", True))),
        storage=StorageConfig(data_dir=Path(storage_raw.get("data_dir", "./data"))),
        logging=LoggingConfig(level=str(logging_raw.get("level", "INFO"))),
    )