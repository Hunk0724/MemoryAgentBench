"""
Burst-probe candidate Gemini models for rate-limit behavior.
Fires 20 short concurrent calls per model and reports timing + any 429s.
"""
import os
import time
import dotenv
import concurrent.futures as cf

dotenv.load_dotenv("/home/yhchiang/MemoryAgentBench/.env")

from google import genai
from google.genai import types
from google.genai.errors import ClientError

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = "global"

CANDIDATES = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
N_CALLS = 20
CONCURRENCY = 10
PROMPT = "Reply with the single word: ok"

def call(model):
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    cfg = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=8,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    t0 = time.time()
    try:
        r = client.models.generate_content(model=model, contents=PROMPT, config=cfg)
        return ("ok", time.time() - t0, r.usage_metadata.prompt_token_count, r.usage_metadata.candidates_token_count)
    except ClientError as e:
        return (f"err{getattr(e,'code','?')}", time.time() - t0, 0, 0)
    except Exception as e:
        return (type(e).__name__, time.time() - t0, 0, 0)

for model in CANDIDATES:
    print(f"\n=== {model} ({N_CALLS} calls, concurrency {CONCURRENCY}) ===")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        results = list(ex.map(lambda _: call(model), range(N_CALLS)))
    dur = time.time() - t0
    statuses = [r[0] for r in results]
    okcount = statuses.count("ok")
    err_counts = {}
    for s in statuses:
        if s != "ok":
            err_counts[s] = err_counts.get(s, 0) + 1
    latencies = sorted(r[1] for r in results if r[0] == "ok")
    p50 = latencies[len(latencies)//2] if latencies else float("nan")
    p95 = latencies[int(len(latencies)*0.95)] if latencies else float("nan")
    throughput = okcount / dur if dur > 0 else 0
    print(f"  total={dur:.1f}s  ok={okcount}/{N_CALLS}  throughput={throughput:.1f} req/s  p50={p50:.2f}s p95={p95:.2f}s")
    if err_counts:
        print(f"  errors: {err_counts}")
