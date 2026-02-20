"""
run_seller_server.py
--------------------
Entry point for the Seller Frontend REST server.
Run with: python run_seller_server.py

Environment variables:
  CUSTOMER_HOST        — Customer DB VM IP (default: localhost)
  PRODUCT_HOST         — Product DB VM IP  (default: localhost)
  CUSTOMER_SELLER_PORT — Seller account port on Customer DB (default: 50053)
  PRODUCT_PORT         — Product DB gRPC port (default: 50052)
  SELLER_PORT          — Port this server listens on (default: 8001)
  SELLER_HOST          — Host to bind to (default: 0.0.0.0)
"""

import os
import uvicorn

from src.frontend.seller_rest_server import app
from src.common.config import load_config
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
args = parser.parse_args()

cfg = load_config(args.config)
if __name__ == "__main__":
    host = cfg.frontend_seller.host
    port = cfg.frontend_seller.port
    print(f"Starting Seller REST server on {host}:{port}")
    print(f"  Customer DB : {cfg.backend_customer_db.host}:{cfg.backend_customer_db.seller_port}")
    print(f"  Product DB  : {cfg.backend_product_db.host}:{cfg.backend_product_db.port}")
    uvicorn.run(app, host=host, port=port)