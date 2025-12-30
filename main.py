from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

client = httpx.AsyncClient()

# ---------------------------
# MODELS
# ---------------------------
class PaidOrderPayload(BaseModel):
    email: EmailStr
    service_id: str
    target_url: str
    quantity: int
    amount: float  # total paid amount (validated by DB trigger)

# ---------------------------
# HELPERS
# ---------------------------
async def get_or_create_customer(email: str) -> str:
    # Try fetch existing customer
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/customers?email=eq.{email}&select=id",
        headers=HEADERS
    )

    if r.status_code != 200:
        raise HTTPException(500, "Customer lookup failed")

    data = r.json()
    if data:
        return data[0]["id"]

    # Insert new customer
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/customers",
        headers=HEADERS,
        json={"email": email}
    )

    if r.status_code not in (200, 201):
        raise HTTPException(500, "Customer creation failed")

    return r.json()[0]["id"]

# ---------------------------
# PAYMENT WEBHOOK (ENTRY POINT)
# ---------------------------
@app.post("/webhook/payment-success")
async def payment_success(payload: PaidOrderPayload):
    """
    This endpoint MUST be called only after payment is confirmed.
    Example: Stripe / Razorpay webhook
    """

    # 1️⃣ Get or create customer
    customer_id = await get_or_create_customer(payload.email)

    # 2️⃣ Create order (DB triggers validate quantity + amount)
    order_data = {
        "customer_id": customer_id,
        "service_id": payload.service_id,
        "target_url": payload.target_url,
        "quantity": payload.quantity,
        "amount": payload.amount,
        "status": "paid"
    }

    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/orders",
        headers=HEADERS,
        json=order_data
    )

    if r.status_code not in (200, 201):
        raise HTTPException(400, f"Order creation failed: {r.text}")

    order = r.json()[0]

    return {
        "success": True,
        "order_id": order["id"],
        "status": order["status"]
    }
