"""Probe gemini-1.5-flash family availability in fc-mh-494213."""
import os, dotenv
dotenv.load_dotenv("/home/yhchiang/MemoryAgentBench/.env")

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
MODELS = [
    "gemini-1.5-flash-latest",   # AI Studio alias style
    "gemini-1.5-flash",          # bare name
    "gemini-1.5-flash-001",      # versioned
    "gemini-1.5-flash-002",      # latest stable
    "gemini-1.5-flash-8b",       # smaller variant
    "gemini-1.5-pro-002",        # control: known to be in the list
]
LOCATIONS = ["global", "us-central1"]
PROMPT = "Reply with the single word: ok"

def probe(model, location):
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=location)
        cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=8)
        r = client.models.generate_content(model=model, contents=PROMPT, config=cfg)
        return f"OK  text={(r.text or '').strip()!r}"
    except (ClientError, ServerError) as e:
        code = getattr(e, "code", "?")
        msg = str(e).splitlines()[0][:80]
        return f"Err {code} {msg}"
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:80]}"

cw = 60
print(f"{'model':<26} " + " | ".join(f"{loc:<{cw}}" for loc in LOCATIONS))
print("-" * (26 + len(LOCATIONS) * (cw + 3)))
for m in MODELS:
    cells = [f"{probe(m, loc):<{cw}}" for loc in LOCATIONS]
    print(f"{m:<26} " + " | ".join(cells))
