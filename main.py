"""crypto-swap: comparador de rutas de swap multi-chain, cobrado por
consulta vía x402 en Algorand (facilitator.goplausible.xyz).
"""
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from lifi_client import get_best_route, summarize_route
from x402_gate import PaymentGate, SwapConfig

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['GET'],
    allow_headers=['PAYMENT-SIGNATURE'],
    expose_headers=['PAYMENT-REQUIRED', 'PAYMENT-RESPONSE'],
)
cfg = SwapConfig()
gate = PaymentGate(cfg)


@app.on_event('startup')
def check_sponsor():
    gate.check_fee_sponsor()


@app.get('/quote')
async def quote(
    from_chain: str = Query(..., description="Chain ID origen (ej. 1=Ethereum) o 'BTC'"),
    from_token: str = Query(..., description="Símbolo, dirección del token origen, o 'bitcoin'"),
    to_chain: str = Query(..., description="Chain ID destino o 'BTC'"),
    to_token: str = Query(..., description="Símbolo, dirección del token destino, o 'bitcoin'"),
    from_amount: str = Query(..., description='Cantidad en unidad mínima (wei/satoshis)'),
    from_address: str = Query(..., description='Wallet de origen'),
    to_address: str | None = Query(default=None, description='Wallet de destino (por defecto, from_address)'),
    payment_signature: str | None = Header(default=None, alias='PAYMENT-SIGNATURE'),
):
    try:
        status, headers = await run_in_threadpool(gate.verify_and_settle, '/quote', payment_signature)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    if status != 200:
        detail = 'payment_required' if status == 402 else 'settlement_pending'
        raise HTTPException(status_code=status, detail=detail, headers=headers)

    raw_quote = await get_best_route(from_chain, from_token, to_chain, to_token, from_amount, from_address, to_address)
    return JSONResponse(summarize_route(raw_quote), headers=headers)
