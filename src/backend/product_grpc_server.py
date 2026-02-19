"""
product_grpc_server.py
----------------------
Runs on the Product DB VM (port 50052).
Does NOT store sessions locally.
Calls Customer DB (ValidateSession) over gRPC to verify tokens.
This is what makes separate VM / separate process deployment work.
"""

import asyncio
import grpc
import os
from concurrent import futures

from src.proto import product_pb2, product_pb2_grpc
from src.proto import customer_pb2, customer_pb2_grpc
from src.server.state import MarketState
from src.server.handlers import buyer, seller

# Product DB's own state (items, cart, inventory)
_SHARED_STATE = MarketState()

# Customer DB address — set via env var for VM deployment
CUSTOMER_HOST = os.getenv("CUSTOMER_HOST", "localhost")
CUSTOMER_BUYER_PORT  = int(os.getenv("CUSTOMER_BUYER_PORT",  "50051"))
CUSTOMER_SELLER_PORT = int(os.getenv("CUSTOMER_SELLER_PORT", "50053"))

# gRPC stubs to call Customer DB for session validation
_buyer_channel  = grpc.insecure_channel(f"{CUSTOMER_HOST}:{CUSTOMER_BUYER_PORT}")
_seller_channel = grpc.insecure_channel(f"{CUSTOMER_HOST}:{CUSTOMER_SELLER_PORT}")
_buyer_customer_stub  = customer_pb2_grpc.CustomerServiceStub(_buyer_channel)
_seller_customer_stub = customer_pb2_grpc.CustomerServiceStub(_seller_channel)


def validate_session(session_token: str, expected_role: str) -> tuple[bool, int]:
    """
    Calls Customer DB to validate session token.
    Returns (is_valid, principal_id).
    Uses buyer stub for 'buyer' role, seller stub for 'seller' role.
    """
    try:
        stub = _buyer_customer_stub if expected_role == "buyer" else _seller_customer_stub
        info = stub.ValidateSession(
            customer_pb2.SessionRequest(session_token=session_token)
        )
        if not info.valid or info.role != expected_role:
            return False, 0
        return True, int(info.principal_id)
    except grpc.RpcError:
        return False, 0


class ProductService(product_pb2_grpc.ProductServiceServicer):

    def __init__(self, state: MarketState):
        self.state = state

    def _run(self, handler, req_dict):
        return asyncio.run(handler(self.state, req_dict))

    def _inject_session(self, req_dict: dict, session_token: str,
                        principal_id: int, role: str) -> dict:
        """
        Injects validated session info into the request so handlers
        don't need to re-validate — they just trust principal_id.
        We store a temporary session in local state for the duration
        of this request so existing handler logic works unchanged.
        """
        # Create a temporary local session entry so handlers find it
        asyncio.run(self.state.db._sessions.__setitem__(
            session_token,
            {"principal_id": principal_id, "role": role,
             "created_at": __import__("time").time()}
        ) if False else self._ensure_local_session(session_token, principal_id, role))
        return req_dict

    def _ensure_local_session(self, token: str, principal_id: int, role: str):
        """Write a local session so handler auth checks pass."""
        import time
        self.state.db._sessions[token] = {
            "principal_id": principal_id,
            "role": role,
            "created_at": time.time()
        }

    # ==================================================
    # SELLER APIs
    # ==================================================

    def RegisterItem(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")

        resp = self._run(seller.handle, {
            "req_id": "grpc_register_item",
            "action": "RegisterItemForSale",
            "data": {
                "item_name": request.name,
                "item_category": request.category,
                "sale_price": request.price,
                "quantity": request.quantity,
                "keywords": [],
                "condition": "new",
                "session_token": request.session_token,
            }
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        item_id = resp["data"]["item_id"]
        return product_pb2.RegisterItemResponse(
            item_id=f"{item_id['category']}:{item_id['number']}"
        )

    def ChangePrice(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")

        resp = self._run(seller.handle, {
            "req_id": "grpc_change_price", "action": "ChangeItemPrice",
            "data": {"item_id": request.item_id, "new_price": request.new_price,
                     "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def UpdateQuantity(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")

        resp = self._run(seller.handle, {
            "req_id": "grpc_update_quantity", "action": "UpdateUnitsForSale",
            "data": {"item_id": request.item_id, "quantity": request.quantity,
                     "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def DisplayItemsForSale(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")

        resp = self._run(seller.handle, {
            "req_id": "grpc_display_items", "action": "DisplayItemsForSale",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        proto_items = [
            product_pb2.ItemResponse(
                item_id=f"{it['item_id']['category']}:{it['item_id']['number']}",
                name=it["name"], price=it["sale_price"], quantity=it["quantity"],
            )
            for it in resp["data"]["items"]
        ]
        return product_pb2.ItemList(items=proto_items)

    # ==================================================
    # BUYER PRODUCT APIs
    # ==================================================

    def SearchItems(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_search", "action": "SearchItemsForSale",
            "data": {"item_category": request.category, "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        proto_items = [
            product_pb2.ItemResponse(
                item_id=f"{it['item_id']['category']}:{it['item_id']['number']}",
                name=it["name"], price=it["sale_price"], quantity=it["quantity"],
            )
            for it in resp["data"]["items"]
        ]
        return product_pb2.ItemList(items=proto_items)

    def GetItem(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_get_item", "action": "GetItem",
            "data": {"item_id": request.item_id, "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        it = resp["data"]["item"]
        return product_pb2.ItemResponse(
            item_id=f"{it['item_id']['category']}:{it['item_id']['number']}",
            name=it["name"], price=it["sale_price"], quantity=it["quantity"],
        )

    # ==================================================
    # CART APIs
    # ==================================================

    def AddToCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_add_to_cart", "action": "AddItemToCart",
            "data": {"item_id": request.item_id, "quantity": request.quantity,
                     "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def RemoveFromCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_remove_from_cart", "action": "RemoveItemFromCart",
            "data": {"item_id": request.item_id, "quantity": request.quantity,
                     "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def SaveCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_save_cart", "action": "SaveCart",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def ClearCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_clear_cart", "action": "ClearCart",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    def GetCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_get_cart", "action": "DisplayCart",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        proto_items = [
            product_pb2.CartItem(
                item_id=f"{ci['item_id']['category']}:{ci['item_id']['number']}",
                quantity=ci["quantity"],
            )
            for ci in resp["data"]["cart"]
        ]
        return product_pb2.CartResponse(items=proto_items)

    # ==================================================
    # FEEDBACK
    # ==================================================

    def ProvideFeedback(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_provide_feedback", "action": "ProvideFeedback",
            "data": {"item_id": request.item_id, "feedback": request.feedback,
                     "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        return product_pb2.Empty()

    # ==================================================
    # PURCHASE (PA2)
    # ==================================================

    def FinalizePurchase(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")

        resp = self._run(buyer.handle, {
            "req_id": "grpc_finalize_purchase", "action": "MakePurchase",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            return product_pb2.PurchaseResult(
                success=False, message=resp.get("error", "Purchase failed")
            )

        # Notify Customer DB to record purchase history
        try:
            total_units = sum(
                line.get("qty", 1)
                for line in resp["data"]["transaction"].get("items", [])
            )
            _buyer_customer_stub.RecordPurchase(
                customer_pb2.RecordPurchaseRequest(
                    session_token=request.session_token,
                    total_units=total_units
                )
            )
        except grpc.RpcError:
            pass  # non-fatal — purchase still succeeded

        return product_pb2.PurchaseResult(
            success=True, message="Purchase completed successfully"
        )


def serve():
    port = int(os.getenv("PRODUCT_PORT", "50052"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    product_pb2_grpc.add_ProductServiceServicer_to_server(
        ProductService(_SHARED_STATE), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"Product gRPC server listening on port {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()