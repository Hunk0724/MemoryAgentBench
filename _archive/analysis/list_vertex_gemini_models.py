"""List all Gemini models available in this Vertex AI project."""
import os
import dotenv
dotenv.load_dotenv("/home/yhchiang/MemoryAgentBench/.env")

from google import genai

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")

for location in ["global", "us-central1"]:
    print(f"\n=== location={location} ===")
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=location)
        models = list(client.models.list())
        names = sorted({m.name.split("/")[-1] for m in models if "gemini" in m.name.lower()})
        for n in names:
            print(f"  {n}")
        print(f"  (total gemini-ish: {len(names)})")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
