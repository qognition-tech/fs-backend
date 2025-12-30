from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

SMM_API_URL = "https://cheapestsmmpanels.com/api/v2"

client = httpx.AsyncClient(timeout=30)

# ---------------------------
# Models
# ---------------------------
class PaidOrderPayload(BaseModel):
    email: EmailStr
    service_uuid: str       # UUID of service in Supabase
    target_url: str
    quantity: int
    amount: float           # total paid amount


# ---------------------------
# Helpers
# ---------------------------
async def get_or_create_customer(email: str) -> str:
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/customers?email=eq.{email}&select=id",
        headers=SUPABASE_HEADERS
    )
    if r.status_code != 200:
        raise HTTPException(500, "Customer lookup failed")

    data = r.json()
    if data:
        return data[0]["id"]

    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/customers",
        headers=SUPABASE_HEADERS,
        json={"email": email}
    )
    if r.status_code not in (200, 201):
        raise HTTPException(500, "Customer creation failed")

    return r.json()[0]["id"]


async def get_service(service_uuid: str):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/services?id=eq.{service_uuid}",
        headers=SUPABASE_HEADERS
    )
    if r.status_code != 200 or not r.json():
        raise HTTPException(404, "Service not found")
    return r.json()[0]


async def get_server_api_key(server_uuid: str):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/servers?id=eq.{server_uuid}",
        headers=SUPABASE_HEADERS
    )
    if r.status_code != 200 or not r.json():
        raise HTTPException(500, "Server API key not found")
    return r.json()[0]["api_key"]


async def send_order_to_smm(api_key: str, service_id: int, link: str, quantity: int):
    payload = {
        "key": api_key,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity
    }
    r = await client.post(SMM_API_URL, data=payload)
    if r.status_code != 200:
        raise HTTPException(502, "SMM panel API error")
    data = r.json()
    if "order" not in data:
        raise HTTPException(400, f"SMM order failed: {data}")
    return data["order"]


# ---------------------------
# Payment webhook endpoint
# ---------------------------
@app.post("/webhook/payment-success")
async def payment_success(payload: PaidOrderPayload):
    # 1️⃣ Get or create customer
    customer_id = await get_or_create_customer(payload.email)

    # 2️⃣ Get service
    service = await get_service(payload.service_uuid)

    # 3️⃣ Create order in Supabase
    order_payload = {
        "customer_id": customer_id,
        "service_id": service["id"],
        "target_url": payload.target_url,
        "quantity": payload.quantity,
        "amount": payload.amount,
        "status": "paid"
    }
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/orders",
        headers=SUPABASE_HEADERS,
        json=order_payload
    )
    if r.status_code not in (200, 201):
        raise HTTPException(400, f"Order creation failed: {r.text}")
    order = r.json()[0]

    # 4️⃣ Get API key from server
    api_key = await get_server_api_key(service["server_id"])

    # 5️⃣ Send order to SMM panel
    external_order_id = await send_order_to_smm(
        api_key=api_key,
        service_id=service["service_id"],  # integer ID for panel
        link=payload.target_url,
        quantity=payload.quantity
    )

    # 6️⃣ Update order with external order ID
    await client.patch(
        f"{SUPABASE_URL}/rest/v1/orders?id=eq.{order['id']}",
        headers=SUPABASE_HEADERS,
        json={"status": "processing", "external_order_id": external_order_id}
    )

    return {
        "success": True,
        "order_id": order["id"],
        "panel_order_id": external_order_id
    }
