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

if __name__ == "__main__":
    host = os.getenv("BUYER_HOST", "0.0.0.0")
    port = int(os.getenv("BUYER_PORT", "8002"))
    print(f"Starting Buyer REST server on {host}:{port}")
    print(f"  Customer DB : {os.getenv('CUSTOMER_HOST', 'localhost')}:{os.getenv('CUSTOMER_BUYER_PORT', '50051')}")
    print(f"  Product DB  : {os.getenv('PRODUCT_HOST',  'localhost')}:{os.getenv('PRODUCT_PORT', '50052')}")
    print(f"  SOAP        : {os.getenv('SOAP_HOST', 'localhost')}:{os.getenv('SOAP_PORT', '8000')}")
    uvicorn.run(app, host=host, port=port)