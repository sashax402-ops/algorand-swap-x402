"""crypto-swap: comparador de rutas de swap multi-chain, cobrado por
consulta vía x402 en Algorand (facilitator.goplausible.xyz).
"""
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lifi_client import get_best_route, summarize_route
from x402_gate import PaymentGate, SwapConfig

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['GET', 'POST'],
    allow_headers=['PAYMENT-SIGNATURE', 'Content-Type'],
    expose_headers=['PAYMENT-REQUIRED', 'PAYMENT-RESPONSE'],
)
cfg = SwapConfig()
gate = PaymentGate(cfg)


class PrepareRequest(BaseModel):
    address: str


@app.get('/config')
async def public_config():
    """Config pública para que la web sepa contra qué validar (red, activo, destinatario)."""
    return {'network': cfg.chain, 'asset': cfg.asset, 'pay_to': cfg.pay_to, 'price_atomic': cfg.price}


@app.post('/prepare-payment')
async def prepare_payment(body: PrepareRequest):
    try:
        return await run_in_threadpool(gate.prepare, body.address, '/execute')
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@app.on_event('startup')
def check_sponsor():
    gate.check_fee_sponsor()


@app.get('/quote')
async def quote_preview(
    from_chain: str = Query(..., description="Chain ID origen (ej. 1=Ethereum) o 'BTC'"),
    from_token: str = Query(..., description="Símbolo, dirección del token origen, o 'bitcoin'"),
    to_chain: str = Query(..., description="Chain ID destino o 'BTC'"),
    to_token: str = Query(..., description="Símbolo, dirección del token destino, o 'bitcoin'"),
    from_amount: str = Query(..., description='Cantidad en unidad mínima (wei/satoshis)'),
    from_address: str = Query(..., description='Wallet de origen'),
    to_address: str | None = Query(default=None, description='Wallet de destino (por defecto, from_address)'),
):
    """Vista previa GRATIS: solo estimación, sin datos ejecutables. Sirve para
    actualizar 'Recibes' en vivo mientras el usuario elige, sin cobrar nada."""
    raw_quote = await get_best_route(from_chain, from_token, to_chain, to_token, from_amount, from_address, to_address)
    full = summarize_route(raw_quote)
    return {k: v for k, v in full.items() if k not in ('transaction_request', 'approval_address')}


@app.get('/execute')
async def execute(
    from_chain: str = Query(...),
    from_token: str = Query(...),
    to_chain: str = Query(...),
    to_token: str = Query(...),
    from_amount: str = Query(...),
    from_address: str = Query(...),
    to_address: str | None = Query(default=None),
    payment_signature: str | None = Header(default=None, alias='PAYMENT-SIGNATURE'),
):
    """Igual que /quote, pero cobra la comisión x402 y devuelve la transacción
    ejecutable (transaction_request). Aquí es donde se paga, no en /quote."""
    try:
        status, headers = await run_in_threadpool(gate.verify_and_settle, '/execute', payment_signature)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    if status != 200:
        detail = 'payment_required' if status == 402 else 'settlement_pending'
        raise HTTPException(status_code=status, detail=detail, headers=headers)

    raw_quote = await get_best_route(from_chain, from_token, to_chain, to_token, from_amount, from_address, to_address)
    return JSONResponse(summarize_route(raw_quote), headers=headers)
