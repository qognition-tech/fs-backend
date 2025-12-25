from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

# ✅ ADD THIS BLOCK
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://followerspike.lovable.app",  # production frontend
        "http://localhost:8080",              # local dev (optional)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ✅ END CORS BLOCK

SMM_API_URL = "https://cheapestsmmpanels.com/api/v2"
ALLOWED_SERVICES = [234]

class Order(BaseModel):
    order_id: str
    service_id: int
    link: str
    quantity: int
    runs: int | None = None
    interval: int | None = None

@app.post("/create-order")
async def create_order(order: Order):
    if order.service_id not in ALLOWED_SERVICES:
        raise HTTPException(status_code=403, detail="Service not allowed")

    payload = {
        "key": os.environ.get("SMM_API_KEY"),
        "action": "add",
        "service": str(order.service_id),
        "link": order.link,
        "quantity": str(order.quantity),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(SMM_API_URL, data=payload)
        supplier = resp.json()

    if resp.status_code != 200 or "error" in supplier:
        raise HTTPException(status_code=502, detail=supplier)

    return {
        "status": "success",
        "local_order_id": order.order_id,
        "supplier_order_id": supplier.get("order"),
        "raw_supplier_response": supplier,
    }
