from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import grpc
import os

from src.proto import customer_pb2, customer_pb2_grpc
from src.proto import product_pb2, product_pb2_grpc
from src.financial.soap_client import SOAPClient

app = FastAPI()

# -------------------------------------------------
# VM Configurable gRPC Connections
# Buyer account ops → Customer DB port 50051
# Product ops       → Product DB port 50052
# -------------------------------------------------

CUSTOMER_HOST       = os.getenv("CUSTOMER_HOST",       "localhost")
PRODUCT_HOST        = os.getenv("PRODUCT_HOST",        "localhost")
SOAP_HOST           = os.getenv("SOAP_HOST",           "localhost")
CUSTOMER_BUYER_PORT = int(os.getenv("CUSTOMER_BUYER_PORT", "50051"))
PRODUCT_PORT        = int(os.getenv("PRODUCT_PORT",        "50052"))
SOAP_PORT           = int(os.getenv("SOAP_PORT",           "8000"))

customer_channel = grpc.insecure_channel(f"{CUSTOMER_HOST}:{CUSTOMER_BUYER_PORT}")
product_channel  = grpc.insecure_channel(f"{PRODUCT_HOST}:{PRODUCT_PORT}")

customer_stub = customer_pb2_grpc.CustomerServiceStub(customer_channel)
product_stub  = product_pb2_grpc.ProductServiceStub(product_channel)

soap_client = SOAPClient(f"http://{SOAP_HOST}:{SOAP_PORT}/?wsdl")

# -------------------------------------------------
# Request Models
# -------------------------------------------------

class AccountRequest(BaseModel):
    username: str
    password: str

class SessionRequest(BaseModel):
    session_token: str

class SearchRequestModel(BaseModel):
    item_category: int
    session_token: str

class ItemRequestModel(BaseModel):
    item_id: str
    session_token: str

class CartRequestModel(BaseModel):
    item_id: str
    quantity: int
    session_token: str

class SellerRatingRequest(BaseModel):
    seller_id: int
    session_token: str

class FeedbackRequestModel(BaseModel):
    item_id: str
    feedback: str
    session_token: str

class PurchaseRequest(BaseModel):
    session_token: str
    card_name: str
    card_number: str
    expiration: str
    security_code: str

# -------------------------------------------------
# Account APIs
# -------------------------------------------------

@app.post("/buyer/create_account")
def create_account(req: AccountRequest):
    try:
        response = customer_stub.CreateAccount(
            customer_pb2.CreateAccountRequest(
                username=req.username, password=req.password
            )
        )
        return {"buyer_id": response.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/login")
def login(req: AccountRequest):
    try:
        response = customer_stub.Login(
            customer_pb2.LoginRequest(
                username=req.username, password=req.password
            )
        )
        return {"session_token": response.session_token, "buyer_id": response.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=e.details())


@app.post("/buyer/logout")
def logout(req: SessionRequest):
    try:
        customer_stub.Logout(
            customer_pb2.SessionRequest(session_token=req.session_token)
        )
        return {"status": "logged_out"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


# -------------------------------------------------
# Product Search APIs
# -------------------------------------------------

@app.post("/buyer/search")
def search_items(req: SearchRequestModel):
    try:
        response = product_stub.SearchItems(
            product_pb2.SearchRequest(
                category=req.item_category,
                session_token=req.session_token
            )
        )
        return {
            "items": [
                {"item_id": item.item_id, "name": item.name,
                 "price": item.price, "quantity": item.quantity}
                for item in response.items
            ]
        }
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/get_item")
def get_item(req: ItemRequestModel):
    try:
        item = product_stub.GetItem(
            product_pb2.ItemRequest(
                item_id=req.item_id, session_token=req.session_token
            )
        )
        return {"item_id": item.item_id, "name": item.name,
                "price": item.price, "quantity": item.quantity}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


# -------------------------------------------------
# Cart APIs
# -------------------------------------------------

@app.post("/buyer/add_to_cart")
def add_to_cart(req: CartRequestModel):
    try:
        product_stub.AddToCart(
            product_pb2.CartRequest(
                item_id=req.item_id, quantity=req.quantity,
                session_token=req.session_token
            )
        )
        return {"status": "added_to_cart"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/remove_from_cart")
def remove_from_cart(req: CartRequestModel):
    try:
        product_stub.RemoveFromCart(
            product_pb2.CartRequest(
                item_id=req.item_id, quantity=req.quantity,
                session_token=req.session_token
            )
        )
        return {"status": "removed_from_cart"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/save_cart")
def save_cart(req: SessionRequest):
    try:
        product_stub.SaveCart(
            product_pb2.SessionRequest(session_token=req.session_token)
        )
        return {"status": "cart_saved"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/clear_cart")
def clear_cart(req: SessionRequest):
    try:
        product_stub.ClearCart(
            product_pb2.SessionRequest(session_token=req.session_token)
        )
        return {"status": "cart_cleared"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/display_cart")
def get_cart(req: SessionRequest):
    try:
        response = product_stub.GetCart(
            product_pb2.SessionRequest(session_token=req.session_token)
        )
        return {
            "cart": [
                {"item_id": item.item_id, "quantity": item.quantity}
                for item in response.items
            ]
        }
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


# -------------------------------------------------
# Feedback
# -------------------------------------------------

@app.post("/buyer/provide_feedback")
def provide_feedback(req: FeedbackRequestModel):
    try:
        product_stub.ProvideFeedback(
            product_pb2.FeedbackRequest(
                item_id=req.item_id, feedback=req.feedback,
                session_token=req.session_token
            )
        )
        return {"status": "feedback_recorded"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/buyer/get_seller_rating")
def get_seller_rating(req: SellerRatingRequest):
    try:
        response = customer_stub.GetSellerRating(
            customer_pb2.SessionSellerRequest(
                seller_id=req.seller_id,
                session_token=req.session_token
            )
        )
        return {"thumbs_up": response.thumbs_up, "thumbs_down": response.thumbs_down}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


# -------------------------------------------------
# Purchase History
# -------------------------------------------------

@app.post("/buyer/get_purchases")
def get_purchases(req: SessionRequest):
    try:
        response = customer_stub.GetBuyerPurchases(
            customer_pb2.SessionRequest(session_token=req.session_token)
        )
        return {"item_ids": list(response.item_ids)}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


# -------------------------------------------------
# Purchase (PA2)
# -------------------------------------------------

@app.post("/buyer/make_purchase")
def make_purchase(req: PurchaseRequest):
    # SOAP payment authorization
    try:
        payment_result = soap_client.process_payment(
            req.card_name, req.card_number,
            req.expiration, req.security_code
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Payment service error: {e}")

    if payment_result != "Yes":
        raise HTTPException(status_code=400, detail="Payment declined")

    #  Finalize purchase on Product DB
    try:
        purchase_result = product_stub.FinalizePurchase(
            product_pb2.SessionRequest(session_token=req.session_token)
        )
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())

    if not purchase_result.success:
        raise HTTPException(status_code=400, detail=purchase_result.message)

    return {"status": "purchase_completed"}