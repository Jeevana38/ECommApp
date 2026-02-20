"""
product_grpc_server.py
----------------------
Runs on the Product DB VM (port 50052).
Does NOT store sessions locally.
Calls Customer DB (ValidateSession) over gRPC to verify tokens.
"""

import asyncio
import grpc
from concurrent import futures

from src.proto import product_pb2, product_pb2_grpc
from src.proto import customer_pb2, customer_pb2_grpc
from src.server.state import MarketState
from src.server.handlers import buyer, seller
from src.common.models import Seller, Buyer

import argparse
from src.common.config import load_config

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
args = parser.parse_args()

cfg = load_config(args.config)

_SHARED_STATE = MarketState()

CUSTOMER_HOST        = cfg.backend_customer_db.host
CUSTOMER_BUYER_PORT  = cfg.backend_customer_db.port
CUSTOMER_SELLER_PORT = cfg.backend_customer_db.seller_port

_buyer_channel        = grpc.insecure_channel(f"{CUSTOMER_HOST}:{CUSTOMER_BUYER_PORT}")
_seller_channel       = grpc.insecure_channel(f"{CUSTOMER_HOST}:{CUSTOMER_SELLER_PORT}")
_buyer_customer_stub  = customer_pb2_grpc.CustomerServiceStub(_buyer_channel)
_seller_customer_stub = customer_pb2_grpc.CustomerServiceStub(_seller_channel)


def validate_session(session_token: str, expected_role: str) -> tuple[bool, int]:
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


def _item_to_proto(it: dict) -> product_pb2.ItemResponse:
    """
    Converts a to_public_dict() item to proto.
    to_public_dict() keys: item_id, item_name, item_category,
                           sale_price, item_quantity, seller_id, ...
    """
    iid = it["item_id"]  # {"category": x, "number": y}
    return product_pb2.ItemResponse(
        item_id=f"{iid['category']}:{iid['number']}",
        name=it["item_name"],
        price=float(it["sale_price"]),
        quantity=int(it["item_quantity"]),
    )


def _cart_item_to_proto(ci: dict) -> product_pb2.CartItem:
    """
    Converts a cart entry to proto.
    buyer.py DisplayCart returns: {"item_id": ItemId.to_dict(), "qty": int}
    """
    iid = ci["item_id"]  # {"category": x, "number": y}
    return product_pb2.CartItem(
        item_id=f"{iid['category']}:{iid['number']}",
        quantity=int(ci["qty"]),
    )


class ProductService(product_pb2_grpc.ProductServiceServicer):

    def __init__(self, state: MarketState):
        self.state = state

    def _run(self, handler, req_dict):
        return asyncio.run(handler(self.state, req_dict))

    def _ensure_local_session(self, token: str, principal_id: int, role: str):
        import time
        self.state.db._sessions[token] = {
            "principal_id": principal_id,
            "role": role,
            "created_at": time.time()
        }

    def _ensure_seller(self, seller_id: int):
        async def _create():
            existing = await self.state.db.get_seller(seller_id)
            if not existing:
                async with self.state.db.lock:
                    if seller_id not in self.state.db.sellers_by_id:
                        s = Seller(seller_id=seller_id, name=f"seller_{seller_id}", password_hash="")
                        self.state.db.sellers_by_id[seller_id] = s
        asyncio.run(_create())

    def _ensure_buyer(self, buyer_id: int):
        async def _create():
            existing = await self.state.db.get_buyer(buyer_id)
            if not existing:
                async with self.state.db.lock:
                    if buyer_id not in self.state.db.buyers_by_id:
                        b = Buyer(buyer_id=buyer_id, name=f"buyer_{buyer_id}", password_hash="")
                        self.state.db.buyers_by_id[buyer_id] = b
        asyncio.run(_create())

    # ==================================================
    # SELLER APIs
    # ==================================================

    def RegisterItem(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")
        self._ensure_seller(seller_id)

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
        item_id = resp["data"]["item_id"]  # {"category": x, "number": y}
        return product_pb2.RegisterItemResponse(
            item_id=f"{item_id['category']}:{item_id['number']}"
        )

    def ChangePrice(self, request, context):
        valid, seller_id = validate_session(request.session_token, "seller")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, seller_id, "seller")
        self._ensure_seller(seller_id)

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
        self._ensure_seller(seller_id)

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
        self._ensure_seller(seller_id)

        resp = self._run(seller.handle, {
            "req_id": "grpc_display_items", "action": "DisplayItemsForSale",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        # seller to_public_dict() returns item_name, sale_price, item_quantity
        return product_pb2.ItemList(items=[_item_to_proto(it) for it in resp["data"]["items"]])

    # ==================================================
    # BUYER PRODUCT APIs
    # ==================================================

    def SearchItems(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")
        self._ensure_buyer(buyer_id)

        resp = self._run(buyer.handle, {
            "req_id": "grpc_search", "action": "SearchItemsForSale",
            "data": {"item_category": request.category, "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        # buyer search returns to_public_dict() — item_name, sale_price, item_quantity
        return product_pb2.ItemList(items=[_item_to_proto(it) for it in resp["data"]["items"]])

    def GetItem(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")
        self._ensure_buyer(buyer_id)

        resp = self._run(buyer.handle, {
            "req_id": "grpc_get_item", "action": "GetItem",
            "data": {"item_id": request.item_id, "session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        # GetItem returns {"item": to_public_dict()}
        return _item_to_proto(resp["data"]["item"])

    # ==================================================
    # CART APIs
    # ==================================================

    def AddToCart(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")
        self._ensure_buyer(buyer_id)

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
        self._ensure_buyer(buyer_id)

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
        self._ensure_buyer(buyer_id)

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
        self._ensure_buyer(buyer_id)

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
        self._ensure_buyer(buyer_id)

        resp = self._run(buyer.handle, {
            "req_id": "grpc_get_cart", "action": "DisplayCart",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, resp.get("error", "error"))
        # DisplayCart returns: {"cart": [{"item_id": {...}, "qty": int}]}
        return product_pb2.CartResponse(
            items=[_cart_item_to_proto(ci) for ci in resp["data"]["cart"]]
        )

    # ==================================================
    # FEEDBACK
    # ==================================================

    def ProvideFeedback(self, request, context):
        valid, buyer_id = validate_session(request.session_token, "buyer")
        if not valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or expired session")
        self._ensure_local_session(request.session_token, buyer_id, "buyer")
        self._ensure_buyer(buyer_id)

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
        self._ensure_buyer(buyer_id)

        resp = self._run(buyer.handle, {
            "req_id": "grpc_finalize_purchase", "action": "MakePurchase",
            "data": {"session_token": request.session_token}
        })
        if not resp.get("ok"):
            return product_pb2.PurchaseResult(
                success=False, message=resp.get("error", "Purchase failed")
            )

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
            pass

        return product_pb2.PurchaseResult(
            success=True, message="Purchase completed successfully"
        )


def serve():
    port = cfg.backend_product_db.port
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