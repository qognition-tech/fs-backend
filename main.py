from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

SMM_API_URL = "https://cheapestsmmpanels.com/api/v2"
ALLOWED_SERVICES = [234]  # whitelist

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
        "quantity": str(order.quantity)
    }

    if order.runs:
        payload["runs"] = str(order.runs)
    if order.interval:
        payload["interval"] = str(order.interval)

    async with httpx.AsyncClient() as client:
        resp = await client.post(SMM_API_URL, data=payload)
        try:
            supplier = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="Supplier API returned invalid response")

    if resp.status_code != 200 or "error" in supplier:
        raise HTTPException(status_code=502, detail=supplier)

    return {
        "status": "success",
        "local_order_id": order.order_id,
        "supplier_order_id": supplier.get("order"),
        "raw_supplier_response": supplier
    }
