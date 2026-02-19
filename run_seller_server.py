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

if __name__ == "__main__":
    host = os.getenv("SELLER_HOST", "0.0.0.0")
    port = int(os.getenv("SELLER_PORT", "8001"))
    print(f"Starting Seller REST server on {host}:{port}")
    print(f"  Customer DB : {os.getenv('CUSTOMER_HOST', 'localhost')}:{os.getenv('CUSTOMER_SELLER_PORT', '50053')}")
    print(f"  Product DB  : {os.getenv('PRODUCT_HOST',  'localhost')}:{os.getenv('PRODUCT_PORT', '50052')}")
    uvicorn.run(app, host=host, port=port)