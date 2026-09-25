"""Cliente mínimo para pedir la mejor ruta de swap/bridge a LI.FI.

LI.FI agrega 27 bridges y 31 exchanges en 58 cadenas (EVM, Solana, Bitcoin, SUI).
No hace falta API key para consultas básicas. Docs: https://docs.li.fi/agents/overview
"""
import httpx

LIFI_QUOTE_URL = "https://li.quest/v1/quote"


async def get_best_route(
    from_chain: int,
    from_token: str,
    to_chain: int,
    to_token: str,
    from_amount: str,
    from_address: str,
) -> dict:
    """Devuelve la mejor ruta entre dos tokens (misma cadena o cross-chain).

    from_chain / to_chain: chain IDs (1=Ethereum, 137=Polygon, 42161=Arbitrum, 8453=Base...)
    from_token / to_token: símbolo o dirección de contrato del token
    from_amount: cantidad en la unidad más pequeña del token (wei / unidades atómicas)
    from_address: wallet del usuario final (solo para calcular la ruta, no se ejecuta nada aquí)
    """
    params = {
        "fromChain": from_chain,
        "toChain": to_chain,
        "fromToken": from_token,
        "toToken": to_token,
        "fromAmount": from_amount,
        "fromAddress": from_address,
        "toAddress": from_address,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(LIFI_QUOTE_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def summarize_route(quote: dict) -> dict:
    """Extrae lo esencial de la respuesta de LI.FI para devolverlo al cliente que pagó."""
    estimate = quote.get("estimate", {})
    tool_details = quote.get("toolDetails", {})
    gas_costs_usd = sum(
        float(g["amountUSD"]) for g in estimate.get("gasCosts", []) if g.get("amountUSD")
    )
    return {
        "provider": tool_details.get("name", quote.get("tool")),
        "to_amount": estimate.get("toAmount"),
        "to_amount_usd": estimate.get("toAmountUSD"),
        "estimated_gas_costs_usd": round(gas_costs_usd, 4),
        "estimated_duration_seconds": estimate.get("executionDuration"),
    }
