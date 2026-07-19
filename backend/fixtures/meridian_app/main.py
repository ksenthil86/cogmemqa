"""
Meridian Banking App Stub — ASGI (FastAPI).

Five deterministic endpoints used as the application-under-test for B5
(FunctionalTesterAgent) and application-under-scan for B6 (SecurityTesterAgent).

Intentional Bandit findings (makes the B6 scan non-trivial):
  - SECRET_KEY hardcoded string → B105 (hardcoded_password_string)
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Intentional B105 finding — hardcoded secret for Bandit demo
SECRET_KEY = "meridian-dev-secret-2024"  # noqa: S105

app = FastAPI(title="Meridian Banking Stub", version="0.1.0")


# ── Request / response models ──────────────────────────────────────────────────

class OpenAccountRequest(BaseModel):
    national_id: str
    name: str


class KycVerifyRequest(BaseModel):
    account_id: str


class TransferRequest(BaseModel):
    amount: float
    balance: float


# ── POST /accounts ─────────────────────────────────────────────────────────────

@app.post("/accounts", status_code=201)
async def open_account(body: OpenAccountRequest):
    if body.national_id == "DUPLICATE":
        raise HTTPException(status_code=409, detail="Account already exists")
    account_id = f"acc-{body.national_id[:8].lower()}"
    return JSONResponse(
        status_code=201,
        content={"account_id": account_id, "name": body.name, "status": "PENDING_KYC"},
    )


# ── POST /kyc/verify ───────────────────────────────────────────────────────────

@app.post("/kyc/verify")
async def kyc_verify(body: KycVerifyRequest):
    return {"status": "VERIFIED", "account_id": body.account_id}


# ── POST /transfers ────────────────────────────────────────────────────────────

@app.post("/transfers")
async def transfer_funds(body: TransferRequest):
    if body.amount > body.balance:
        return JSONResponse(
            status_code=402,
            content={"error": "INSUFFICIENT_FUNDS"},
        )
    ref = f"txn-{int(body.amount)}-ok"
    return {"reference": ref, "status": "COMPLETED"}


# ── GET /transactions ──────────────────────────────────────────────────────────

@app.get("/transactions")
async def get_transactions(page: int = Query(default=1)):
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    return [
        {"id": f"txn-{(page - 1) * 20 + i + 1}", "amount": 100 + i, "status": "SETTLED"}
        for i in range(20)
    ]


# ── GET /fraud/alerts ──────────────────────────────────────────────────────────

@app.get("/fraud/alerts")
async def fraud_alerts(amount: Optional[float] = Query(default=0)):
    if amount is not None and amount > 10000:
        return [
            {
                "alert_id": "alert-001",
                "reason": "LARGE_TRANSACTION",
                "amount": amount,
                "risk_score": 0.87,
            }
        ]
    return []
