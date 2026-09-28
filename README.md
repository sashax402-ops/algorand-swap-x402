ChepeastSwap — x402 Swap API
Multi-chain swap and bridge quotes powered by LI.FI, with paid access to transaction data through x402 on Algorand.
ChepeastSwap helps users find a swap route, inspect the estimated output and gas cost, and obtain a transaction they can sign with their own wallet. Developers and automated clients can use the same HTTP API without a subscription or a ChepeastSwap account.
This repository contains the Python backend. The browser application lives in web-algorand-swap-x402.
What it does
- Retrieves swap and bridge quotes from LI.FI.
- Provides free route previews and token price lookups.
- Protects executable transaction data with an x402 v2 payment in Algorand USDC.
- Prepares an unsigned Algorand payment group for the customer's wallet.
- Uses a facilitator to verify and settle the payment, with sponsored Algorand transaction fees.
- Returns a payment receipt in the PAYMENT-RESPONSE header after successful settlement and route retrieval.
- Publishes an x402 discovery manifest, merchant metadata and the x402-global-challenge tag.
The backend does not sign or broadcast the customer's swap. Its /execute endpoint returns a transaction_request; the client signs and submits that transaction on the swap's source chain.
How the two chains fit together
Action	Network / service	Who authorizes it
Preview a route	LI.FI through this API	No payment required
Pay for executable route data	USDC on Algorand	Customer's Algorand wallet
Cover the payment group's network fee	Algorand	Facilitator's advertised fee sponsor
Approve token spending, when needed	Swap's source chain	Customer's source-chain wallet
Submit the swap or bridge transaction	Swap's source chain	Customer's source-chain wallet


Algorand is the service-payment network. Available swap routes depend on LI.FI and the client's signing capabilities. The companion web application currently exposes a fixed selection of EVM networks and tokens.
The API requests a quote from LI.FI; it does not independently guarantee the lowest price across every exchange.
Quick start
Use Python 3.11 or newer and run commands from the repository root. The following examples use Bash, including Linux, macOS and WSL.
git clone https://github.com/sashax402-ops/algorand-swap-x402.git
cd algorand-swap-x402

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
Set the required configuration, replacing the address placeholders with real Algorand addresses:
export ALGORAND_NETWORK='mainnet'
export PAY_TO_ALGORAND_ADDRESS='YOUR_USDC_RECEIVING_ALGORAND_ADDRESS'
export FEE_PAYER_ADDRESS='FACILITATOR_ADVERTISED_FEE_PAYER_ADDRESS'
export SERVICE_URL='http://localhost:8000'
export PRICE_ATOMIC='10000'

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
Open http://localhost:8000/docs for the generated API documentation.
FEE_PAYER_ADDRESS must match the sponsor advertised by the configured facilitator for x402 v2, the exact scheme and the selected Algorand network. It is not an arbitrary wallet address. The application checks this at startup and refuses to start if it does not match. Inspect the facilitator's capabilities with:
curl -sS https://facilitator.goplausible.xyz/supported
The receiving wallet must be able to receive the configured USDC asset. The customer needs USDC on the selected Algorand network and the corresponding asset opt-in. Sponsorship covers the payment group's transaction fees; it does not create or fund the customer's account or perform its asset opt-in.
Environment variables
Variable	Required	Default	Purpose
PAY_TO_ALGORAND_ADDRESS	Yes	—	Recipient of the service payment.
FEE_PAYER_ADDRESS	Yes	—	Fee sponsor advertised by the facilitator.
SERVICE_URL	Yes	—	Public base URL of this API, used in the signed payment resource. Use the API URL, not the frontend URL.
ALGORAND_NETWORK	No	mainnet	mainnet or testnet; selects the network and USDC asset through the SDK constants.
PRICE_ATOMIC	No	10000	Service price in USDC atomic units: 10000 = 0.01 USDC.
FACILITATOR_URL	No	https://facilitator.goplausible.xyz	x402 verification and settlement service.
ALGOD_URL	No	https://<network>-api.algonode.cloud	Algorand node used to obtain transaction parameters.


The code reads environment variables directly; it does not automatically load a .env file. No customer seed phrase, private key or LI.FI API key is configured by this implementation.
For a hosted Python service, install with pip install -r requirements.txt and start with:
uvicorn main:app --host 0.0.0.0 --port "$PORT"
This command assumes the host supplies PORT. Set SERVICE_URL to the deployed API's public HTTPS URL and configure the remaining variables in the host's environment settings.
API reference
Method	Path	Payment	Response
GET	/config	Free	Network, USDC asset, recipient and price.
GET	/price	Free	Informational token price in USD from LI.FI.
GET	/quote	Free	Estimated route, output, gas cost and duration.
POST	/prepare-payment	Free	Unsigned payment group and signing metadata.
GET	/execute	x402	Executable route data after payment settlement.
GET	/.well-known/x402.json	Free	x402 discovery and merchant metadata.


Route parameters
Both /quote and /execute use these query parameters:
Parameter	Required	Meaning
from_chain	Yes	Source chain identifier accepted by LI.FI.
from_token	Yes	Source token symbol or address accepted by LI.FI.
to_chain	Yes	Destination chain identifier.
to_token	Yes	Destination token symbol or address.
from_amount	Yes	Integer amount in the token's smallest unit, supplied as a string.
from_address	Yes	Actual source-chain wallet address.
to_address	No	Destination wallet; defaults to from_address.


For example, 1000000 is one unit of a token with six decimals; it is not one unit of an 18-decimal token. Use addresses valid for the selected chains.
Free requests
curl -sS http://localhost:8000/config

curl -sS --get http://localhost:8000/price \
  --data-urlencode 'chain=1' \
  --data-urlencode 'token=USDC'
Example route preview, using your actual EVM address:
EVM_ADDRESS='YOUR_EVM_WALLET_ADDRESS'

curl -sS --get http://localhost:8000/quote \
  --data-urlencode 'from_chain=1' \
  --data-urlencode 'from_token=USDC' \
  --data-urlencode 'to_chain=8453' \
  --data-urlencode 'to_token=USDC' \
  --data-urlencode 'from_amount=100000000' \
  --data-urlencode "from_address=$EVM_ADDRESS" \
  --data-urlencode "to_address=$EVM_ADDRESS"
The preview contains provider, to_amount, to_amount_usd, estimated_gas_costs_usd and estimated_duration_seconds. It excludes transaction_request and approval_address.
x402 payment flow
1. Request /execute with the route parameters and no payment header. The server responds with 402 Payment Required and a base64 JSON PAYMENT-REQUIRED header. An unsigned request to /execute without query parameters also returns the discovery challenge.
2. Call POST /prepare-payment with {"address":"YOUR_ALGORAND_ADDRESS"}.
3. Validate the returned resource, network, asset, recipient, amount, expiry and transaction group. Ask the customer's wallet to sign only the transaction identified by sign_indexes.
4. Build the x402 v2 payment payload, preserving the unsigned sponsor transaction and including the signed customer transaction. Base64-encode the JSON payload.
5. Repeat the parameterized /execute request with that value in PAYMENT-SIGNATURE.
6. After successful verification, settlement and quote retrieval, read the route JSON and decode PAYMENT-RESPONSE for the settlement receipt.
7. Use the source-chain wallet to approve any required token allowance and submit transaction_request.
The companion application's wallet.js implements client-side payment validation and signing. A standard HTTP client must implement those steps explicitly; receiving a 402 response alone does not make a payment.
Payment and response behavior
- The default service fee is 0.01 USDC per paid request. The configured /config response is authoritative.
- Swap gas, token approvals and provider or bridge costs are separate from the Algorand service fee.
- Payment settlement occurs before the final LI.FI quote is fetched. A later quote failure or cancelled swap does not automatically refund the service payment.
- 400 indicates invalid preparation or payment data; 402 indicates missing or rejected payment; 202 means settlement was not reported successful; 422 indicates invalid request parameters; 502 indicates a handled LI.FI error.
- Treat 202 as pending or unsuccessful settlement, not as executable route data. Check the payment outcome before authorizing another payment.
Repository layout
File	Role
main.py	FastAPI routes, CORS, payment challenge middleware and startup check.
lifi_client.py	LI.FI quote retrieval and response summarization.
x402_gate.py	Configuration, unsigned payment construction, validation and settlement.
requirements.txt	Pinned Python dependencies.
validation.js	Standalone client-validation source; currently references /quote, whereas the active paid endpoint is /execute. Do not use it unchanged for that endpoint.
APLICAR.md	Notes about a separate news project; not installation instructions for this API.


The JavaScript validation used by the current web application is bundled in its own wallet.js and checks /execute.
Troubleshooting
Symptom	Check
Missing environment variable at startup	Set all three required configuration variables before importing or starting the app.
Facilitator does not advertise this fee sponsor on this network	Match the sponsor, facilitator and Algorand network to the facilitator's advertised capabilities.
Payment differs from the request	Compare /config, SERVICE_URL, the challenge and the signed payment. Regenerate expired payment groups.
LI.FI returns an error	Check chain identifiers, token addresses, token decimals, amount and real wallet addresses. Some pairs have no available route.
Web price conversion fails	Ensure the frontend points to this backend, which includes /price.


Related repository
ChepeastSwap web application — browser interface, EVM wallet interaction and Algorand payment signing.
License
