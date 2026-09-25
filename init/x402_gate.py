"""Puerta de pago x402 para crypto-swap: cobra en Algorand vía
facilitator.goplausible.xyz antes de servir una respuesta.

Las funciones de verificación (check_payment_tx / check_sponsored_group /
validate_payment_payload) y la codificación b64/unb64 están tomadas de
agente.py (qts-server) casi tal cual: son el motor x402 genérico -- no
lógica de negocio de QTS -- así que se reutilizan en vez de reescribirse.
Simplificación respecto al original: aquí el "payer" se obtiene siempre de
la propia transacción firmada, no de una cabecera aparte, porque este
endpoint no necesita rastrear identidad de cliente entre peticiones.
"""
import base64
import json
import os
from copy import deepcopy

from algosdk import encoding, transaction
from algosdk.encoding import is_valid_address
from x402.http import FacilitatorConfig, HTTPFacilitatorClientSync
from x402.mechanisms.avm.constants import (
    ALGORAND_MAINNET_CAIP2,
    ALGORAND_TESTNET_CAIP2,
    USDC_MAINNET_ASA_ID,
    USDC_TESTNET_ASA_ID,
)
from x402.schemas import PaymentPayload, PaymentRequired, PaymentRequirements, ResourceInfo


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)


def b64(obj):
    if hasattr(obj, 'model_dump'):
        obj = obj.model_dump(by_alias=True, exclude_none=True)
    return base64.b64encode(canonical(obj).encode()).decode()


def unb64(value):
    if not value or len(value) > 64000:
        raise ValueError('Invalid payment header')
    return json.loads(base64.b64decode(value, validate=True))


def check_payment_tx(txn, cfg):
    expected = cfg.chain.split(':', 1)[1]
    if (
        txn.type != 'axfer' or txn.receiver != cfg.pay_to or
        txn.amount != cfg.price or str(txn.index) != cfg.asset or
        txn.rekey_to or txn.close_assets_to or txn.revocation_target or
        txn.genesis_hash != expected or txn.fee != 0 or
        not 0 < txn.last_valid_round - txn.first_valid_round <= 1000
    ):
        raise ValueError('Payment does not match the authorized recipient, amount, network and permissions')


def check_sponsored_group(txns, cfg):
    sponsor, payment = txns
    if not cfg.fee_payer or payment.sender == cfg.fee_payer:
        raise ValueError('A separate, pinned network fee sponsor is required')
    check_payment_tx(payment, cfg)
    if (
        sponsor.type != 'pay' or sponsor.sender != cfg.fee_payer or sponsor.receiver != cfg.fee_payer or
        sponsor.amt != 0 or sponsor.close_remainder_to or sponsor.rekey_to or
        not 2000 <= sponsor.fee <= 4000 or sponsor.genesis_hash != payment.genesis_hash or
        sponsor.first_valid_round != payment.first_valid_round or sponsor.last_valid_round != payment.last_valid_round or
        sponsor.lease or payment.lease
    ):
        raise ValueError('Invalid sponsored payment group')
    if not payment.group or sponsor.group != payment.group:
        raise ValueError('Missing or mismatched atomic group')
    unsigned = deepcopy(txns)
    for t in unsigned:
        t.group = None
    if transaction.calculate_group_id(unsigned) != payment.group:
        raise ValueError('Atomic group hash mismatch')
    return payment.sender


def validate_payment_payload(payload, cfg):
    obj = payload.payload if hasattr(payload, 'payload') else payload['payload']
    if obj.get('paymentIndex') != 1 or len(obj.get('paymentGroup', [])) != 2:
        raise ValueError('Expected one sponsor transaction and one USDC payment')
    decoded = [encoding.msgpack_decode(x) for x in obj['paymentGroup']]
    if not isinstance(decoded[0], transaction.PaymentTxn) or not isinstance(decoded[1], transaction.SignedTransaction):
        raise ValueError('Only the USDC payment may be signed by the customer')
    if decoded[1].authorizing_address:
        raise ValueError('Rekeyed payment accounts are not supported')
    txns = [decoded[0], decoded[1].transaction]
    payer = check_sponsored_group(txns, cfg)
    return txns, payer


class SwapConfig:
    """Config vía variables de entorno. Sin fichero de config aparte."""

    def __init__(self):
        network = os.environ.get('ALGORAND_NETWORK', 'mainnet')
        if network not in ('mainnet', 'testnet'):
            raise ValueError('ALGORAND_NETWORK must be mainnet or testnet')
        self.network = network
        self.chain = ALGORAND_MAINNET_CAIP2 if network == 'mainnet' else ALGORAND_TESTNET_CAIP2
        self.asset = str(USDC_MAINNET_ASA_ID if network == 'mainnet' else USDC_TESTNET_ASA_ID)
        self.pay_to = os.environ['PAY_TO_ALGORAND_ADDRESS']
        self.fee_payer = os.environ['FEE_PAYER_ADDRESS']  # el mismo sponsor que ya usas en qts-server
        self.price = int(os.environ.get('PRICE_ATOMIC', '10000'))  # 0.01 USDC (6 decimales)
        self.endpoint = os.environ['SERVICE_URL'].rstrip('/')  # p.ej. https://crypto-swap.onrender.com
        self.facilitator_url = os.environ.get('FACILITATOR_URL', 'https://facilitator.goplausible.xyz')
        if not is_valid_address(self.pay_to) or not is_valid_address(self.fee_payer):
            raise ValueError('PAY_TO_ALGORAND_ADDRESS / FEE_PAYER_ADDRESS must be valid Algorand addresses')


class PaymentGate:
    """Verifica y liquida el pago x402 antes de dejar pasar la petición."""

    def __init__(self, cfg, facilitator=None):
        self.cfg = cfg
        self.facilitator = facilitator or HTTPFacilitatorClientSync(
            FacilitatorConfig(url=cfg.facilitator_url, timeout=12)
        )

    def check_fee_sponsor(self):
        """Falla rápido al arrancar si el facilitador ya no patrocina esta dirección."""
        supported = self.facilitator.get_supported()
        if not any(
            k.network == self.cfg.chain and k.scheme == 'exact' and k.x402_version == 2 and
            (k.extra or {}).get('feePayer') == self.cfg.fee_payer
            for k in supported.kinds
        ):
            raise ValueError('Facilitator does not advertise this fee sponsor on this network')

    def requirement(self, resource_path):
        return PaymentRequirements(
            scheme='exact', network=self.cfg.chain, asset=self.cfg.asset,
            amount=str(self.cfg.price), pay_to=self.cfg.pay_to, max_timeout_seconds=120,
            extra={'feePayer': self.cfg.fee_payer},
        )

    def quote(self, resource_path):
        return PaymentRequired(
            accepts=[self.requirement(resource_path)],
            resource=ResourceInfo(
                url=self.cfg.endpoint + resource_path,
                description='Mejor ruta de swap multi-cadena (LI.FI)',
                mime_type='application/json',
            ),
        )

    def verify_and_settle(self, resource_path, payment_header):
        """Devuelve (status_code, response_headers). status_code 200 = pago liquidado."""
        if not payment_header:
            return 402, {'PAYMENT-REQUIRED': b64(self.quote(resource_path))}

        requirement = self.requirement(resource_path)
        try:
            payload = PaymentPayload.model_validate(unb64(payment_header))
            if payload.x402_version != 2 or payload.accepted != requirement:
                raise ValueError()
            if not payload.resource or payload.resource.url != self.cfg.endpoint + resource_path:
                raise ValueError()
            validate_payment_payload(payload, self.cfg)
        except Exception:
            raise ValueError('Payment differs from the request or is not allowed') from None

        verification = self.facilitator.verify(payload, requirement)
        if not verification.is_valid:
            return 402, {'PAYMENT-REQUIRED': b64(self.quote(resource_path))}

        settle = self.facilitator.settle(payload, requirement)
        if not settle.success:
            return 202, {}

        return 200, {'PAYMENT-RESPONSE': b64(settle)}
