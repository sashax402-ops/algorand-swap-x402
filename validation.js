// Adaptado de Trading News (frontend/validation.js). Único cambio real: la
// ruta protegida es /quote (fija), no /api/v1/report/{symbol}. El resto de
// comprobaciones (red, importe, grupo patrocinado, group ID) son idénticas.
import algosdk from "algosdk";

export function bytes(value) { return Uint8Array.from(atob(value), c => c.charCodeAt(0)); }
export function b64(value) { return btoa(Array.from(value, c => String.fromCharCode(c)).join("")); }
function reject() { throw new Error("La operación no coincide con el precio, la red o la wallet anunciados. No se ha firmado."); }
const sameBytes = (a,b) => a?.length === b?.length && Array.from(a || []).every((v,i) => v === b[i]);

export function validateQuote(q, cfg, payer, origin) {
  const c=q?.challenge, r=c?.accepts?.[0];
  const resource=new URL(c?.resource?.url || "invalid", origin);
  if(c?.x402Version!==2 || c.accepts.length!==1 || resource.origin!==origin ||
      resource.pathname!=="/quote" || resource.search || resource.hash ||
      r.scheme!=="exact" || r.network!==cfg.network_caip || r.asset!==cfg.asset_id || r.payTo!==cfg.pay_to ||
      BigInt(r.amount)!==BigInt(cfg.price_atomic) || q.payer!==payer ||
      q.expires_at*1000<=Date.now()) reject();
  const sponsor=r.extra?.feePayer;
  const ts=q.unsigned_transactions.map(s=>algosdk.decodeUnsignedTransaction(bytes(s)));
  const pi=sponsor?1:0;
  if(ts.length!==(sponsor?2:1) || q.payment_index!==pi || q.sign_indexes.length!==1 || q.sign_indexes[0]!==pi) reject();
  for(const [i,t] of ts.entries()){
    if(t.rekeyTo || b64(t.genesisHash)!==r.network.split(":")[1] ||
       t.txID()!==q.transaction_ids[i] || t.lastValid<=t.firstValid || t.lastValid-t.firstValid>100n) reject();
  }
  const t=ts[pi], a=t.assetTransfer;
  if(t.type!=="axfer" || t.sender.toString()!==payer || a.receiver.toString()!==cfg.pay_to ||
     a.amount!==BigInt(r.amount) || a.assetIndex!==BigInt(cfg.asset_id) || a.closeRemainderTo || a.assetSender ||
     t.fee>10000n || (sponsor && t.fee!==0n) || (!sponsor && t.group)) reject();
  if(sponsor){
    const f=ts[0], p=f.payment;
    if(f.type!=="pay" || f.sender.toString()!==sponsor || p.receiver.toString()!==sponsor ||
       p.amount!==0n || p.closeRemainderTo || f.fee>20000n || f.fee<2000n ||
       !sameBytes(f.group,t.group) || f.firstValid!==t.firstValid || f.lastValid!==t.lastValid) reject();
    const claimed=t.group;
    const ungrouped=ts.map(tx=>algosdk.decodeUnsignedTransaction(algosdk.encodeUnsignedTransaction(tx)));
    ungrouped.forEach(tx=>{tx.group=undefined;});
    if(!sameBytes(algosdk.computeGroupID(ungrouped),claimed)) reject();
  }
  if(Number(t.fee)!==q.customer_network_fee_microalgo || Number(ts.reduce((s,t)=>s+t.fee,0n))!==q.network_fee_microalgo) reject();
  return ts;
}

export function buildSignedPayload(q, signed, payer) {
  const index=q.payment_index, target=q.transaction_ids[index];
  const match=signed.filter(Boolean).map(raw=>({raw, decoded:algosdk.decodeSignedTransaction(raw)}))
    .find(x=>x.decoded.txn.txID()===target);
  if(!match || match.decoded.txn.sender.toString()!==payer || !match.decoded.sig || match.decoded.sgnr) reject();
  const group=[...q.unsigned_transactions];group[index]=b64(match.raw);
  const payload={x402Version:2, accepted:q.challenge.accepts[0],resource:q.challenge.resource,
    extensions:q.challenge.extensions,payload:{paymentGroup:group,paymentIndex:index}};
  return b64(new TextEncoder().encode(JSON.stringify(payload)));
}
