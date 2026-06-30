"""
Probe Vertex AI Gemini candidates for migration off 3.1-flash-lite-preview (sunset 2026-07-09).
"""
import os
import dotenv
dotenv.load_dotenv("/home/yhchiang/MemoryAgentBench/.env")

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
print(f"Project: {PROJECT}\n")

# All Gemini 3.x candidates + relevant 2.5 fallbacks (filtered to non-image/tts/audio)
MODELS = [
    "gemini-3.1-flash-lite-preview",  # current
    "gemini-3.1-flash-lite",          # GA — primary migration target
    "gemini-3-flash-preview",         # preview only
    "gemini-3.5-flash",               # newer GA, not in email
    "gemini-3.1-pro-preview",         # pro 3.x, preview only
    "gemini-2.5-flash",               # GA fallback
    "gemini-2.5-flash-lite",          # GA fallback
    "gemini-2.5-pro",                 # GA pro
]
LOCATIONS = ["global", "us-central1"]
PROMPT = "Reply with the single word: ok"

def probe(model, location):
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=location)
        cfg = types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=16,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        resp = client.models.generate_content(model=model, contents=PROMPT, config=cfg)
        text = (resp.text or "").strip().replace("\n", " ")[:20]
        in_tok = resp.usage_metadata.prompt_token_count
        out_tok = resp.usage_metadata.candidates_token_count
        return f"OK  in={in_tok} out={out_tok} text={text!r}"
    except (ClientError, ServerError) as e:
        code = getattr(e, "code", "?")
        return f"Err {code}"
    except Exception as e:
        return f"{type(e).__name__}"

col_w = 45
print(f"{'model':<32} " + " | ".join(f"{loc:<{col_w}}" for loc in LOCATIONS))
print("-" * (32 + len(LOCATIONS) * (col_w + 3)))
for model in MODELS:
    cells = [f"{probe(model, loc):<{col_w}}" for loc in LOCATIONS]
    print(f"{model:<32} " + " | ".join(cells))
