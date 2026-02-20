"""
run_buyer_server.py
-------------------
Entry point for the Buyer Frontend REST server.
Run with: python run_buyer_server.py

Environment variables:
  CUSTOMER_HOST        — Customer DB VM IP (default: localhost)
  PRODUCT_HOST         — Product DB VM IP  (default: localhost)
  CUSTOMER_BUYER_PORT  — Buyer account port on Customer DB (default: 50051)
  PRODUCT_PORT         — Product DB gRPC port (default: 50052)
  SOAP_HOST            — SOAP service VM IP (default: localhost)
  SOAP_PORT            — SOAP service port   (default: 8000)
  BUYER_PORT           — Port this server listens on (default: 8002)
  BUYER_HOST           — Host to bind to (default: 0.0.0.0)
"""

import os
import uvicorn

from src.frontend.buyer_rest_server import app
import argparse
from src.common.config import load_config

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
args = parser.parse_args()

cfg = load_config(args.config)

if __name__ == "__main__":
    host = cfg.frontend_buyer.host
    port = cfg.frontend_buyer.port
    print(f"Starting Buyer REST server on {host}:{port}")
    print(f"  Customer DB : {cfg.backend_customer_db.host}:{cfg.backend_customer_db.port}")
    print(f"  Product DB  : {cfg.backend_product_db.host}:{cfg.backend_product_db.port}")
    print(f"  SOAP        : {cfg.soap.host}:{cfg.soap.port}")
    uvicorn.run(app, host=host, port=port)