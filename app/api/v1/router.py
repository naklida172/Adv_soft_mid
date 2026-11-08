from fastapi import APIRouter
from app.api.v1.endpoints import payments, wallets, health, dashboard

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(payments.router)
api_v1_router.include_router(wallets.router)
api_v1_router.include_router(dashboard.router)
