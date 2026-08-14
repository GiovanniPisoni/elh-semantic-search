"""Submit one judge batch to the Anthropic Batch API, poll until done, save results."""
import json, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import anthropic

PRICE = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

batch_file = Path(sys.argv[1])
requests = [json.loads(l) for l in batch_file.open(encoding="utf-8")]
print(f"{batch_file.name}: {len(requests)} requests, model={requests[0].get('params',{}).get('model')}")

client = anthropic.Anthropic()
batch = client.messages.batches.create(requests=requests)
print(f"submitted: {batch.id}  status={batch.processing_status}")

while True:
    b = client.messages.batches.retrieve(batch.id)
    c = b.request_counts
    print(f"  {b.processing_status}  succeeded={c.succeeded} errored={c.errored} "
          f"processing={c.processing} canceled={c.canceled} expired={c.expired}", flush=True)
    if b.processing_status == "ended":
        break
    time.sleep(20)

results_dir = batch_file.parent / "results"
results_dir.mkdir(parents=True, exist_ok=True)
out = results_dir / f"results_{batch_file.stem.replace('batch_','')}.jsonl"
tin = tout = 0
n_ok = n_err = 0
with out.open("w", encoding="utf-8") as f:
    for res in client.messages.batches.results(batch.id):
        rec = {"custom_id": res.custom_id, "type": res.result.type}
        if res.result.type == "succeeded":
            m = res.result.message
            rec["text"] = m.content[0].text
            rec["usage"] = {"in": m.usage.input_tokens, "out": m.usage.output_tokens}
            tin += m.usage.input_tokens; tout += m.usage.output_tokens
            n_ok += 1
        else:
            rec["error"] = str(getattr(res.result, "error", res.result.type))
            n_err += 1
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

model = requests[0].get("params", {}).get("model")
pi, po = PRICE.get(model, (3.0, 15.0))
cost = (tin * pi + tout * po) / 1_000_000 * 0.5  # 50% batch discount
print(f"\nDONE  ok={n_ok} err={n_err}  tokens={tin}in/{tout}out")
print(f"ACTUAL COST (batch-discounted): ${cost:.4f}")
print(f"Results: {out}")