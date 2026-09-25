"""crypto-swap: comparador de rutas de swap multi-chain, cobrado por
consulta vía x402 en Algorand (facilitator.goplausible.xyz).
"""
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from lifi_client import get_best_route, summarize_route
from x402_gate import PaymentGate, SwapConfig

app = FastAPI()
cfg = SwapConfig()
gate = PaymentGate(cfg)


@app.on_event('startup')
def check_sponsor():
    gate.check_fee_sponsor()


@app.get('/quote')
async def quote(
    from_chain: int = Query(..., description='Chain ID origen, ej. 1=Ethereum'),
    from_token: str = Query(..., description='Símbolo o dirección del token origen'),
    to_chain: int = Query(..., description='Chain ID destino'),
    to_token: str = Query(..., description='Símbolo o dirección del token destino'),
    from_amount: str = Query(..., description='Cantidad en unidad mínima (wei)'),
    from_address: str = Query(..., description='Wallet del usuario final'),
    payment_signature: str | None = Header(default=None, alias='PAYMENT-SIGNATURE'),
):
    try:
        status, headers = await run_in_threadpool(gate.verify_and_settle, '/quote', payment_signature)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    if status != 200:
        detail = 'payment_required' if status == 402 else 'settlement_pending'
        raise HTTPException(status_code=status, detail=detail, headers=headers)

    raw_quote = await get_best_route(from_chain, from_token, to_chain, to_token, from_amount, from_address)
    return JSONResponse(summarize_route(raw_quote), headers=headers)
