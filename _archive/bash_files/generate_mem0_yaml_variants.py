"""Generate mem0/mem0g yaml variants across (model × chunk_size) from the
gemini-2.5-flash-lite + chunk=4096 base.

Usage:
    python bash_files/generate_mem0_yaml_variants.py

Variants:
  configs/agent_conf/RAG_Agents/Gemini/
    Structure_rag_mem0_<MODEL>_chunk<C>.yaml
    Structure_rag_mem0g_<MODEL>_chunk<C>.yaml
for each (MODEL, C) ∈ MODELS × CHUNK_SIZES.

Notes:
- agent_chunk_size 是 mem0 ingest chunk(memory.add() 切分),不是 dataset chunk
- chunk=512 用於跟 HippoRAG-v2 過去實驗對齊
- chunk=4096 是 mem0 paper / benchmark default
Re-run idempotent.
"""
from pathlib import Path
import re

# 5-model matrix from pilot plan. See:
#   docs/baseline_methods/baseline_methods_paper_vs_impl.md §6.3
#   docs/experiments/pilots/mem0_mem0g_pilot_plan.md
MODELS = [
    # 2026-05-24 dry-run 通過的 5 個 model(Vertex location=global, project=fc-mh-494213):
    "gemini-2.5-flash-lite",            # SOTA cheap, base template
    "gemini-2.5-flash",                 # SOTA standard
    "gemini-3.1-flash-lite",            # 3.1 GA cheap
    "gemini-3.1-flash-lite-preview",    # 過去用的(2026-07-09 sunset),作為 reference
    "gemini-3.5-flash",                 # newest
    # NOTE: gemini-1.5-flash-latest 在 us-central1/global 不可用,已從矩陣移除
]
CHUNK_SIZES = [512, 4096]
BASE_DIR = Path(__file__).resolve().parent.parent / "configs/agent_conf/RAG_Agents/Gemini"
TEMPLATES = [
    ("Structure_rag_mem0_gemini-2.5-flash-lite.yaml",  "mem0"),
    ("Structure_rag_mem0g_gemini-2.5-flash-lite.yaml", "mem0g"),
]
BASE_MODEL = "gemini-2.5-flash-lite"
BASE_CHUNK = 4096


def render(src, model, chunk_size, agent_kind):
    """Replace model + chunk_size + output_dir to produce a variant."""
    new = re.sub(re.escape(BASE_MODEL), model, src)
    # 替換 agent_chunk_size 行
    new = re.sub(
        r"agent_chunk_size:\s*\d+",
        f"agent_chunk_size: {chunk_size}",
        new,
    )
    # 替換 agent_name 加 chunk 後綴
    new = re.sub(
        rf"^agent_name:\s*Structure_rag_{agent_kind}_{model}\s*$",
        f"agent_name: Structure_rag_{agent_kind}_{model}_chunk{chunk_size}",
        new,
        flags=re.MULTILINE,
    )
    # 替換 output_dir 加 chunk 後綴
    new = re.sub(
        rf"output_dir:.*$",
        f"output_dir: ./outputs/{model}-{agent_kind}-chunk{chunk_size}",
        new,
        flags=re.MULTILINE,
    )
    return new


def main():
    for tpl_name, kind in TEMPLATES:
        src = (BASE_DIR / tpl_name).read_text()
        for model in MODELS:
            for chunk in CHUNK_SIZES:
                out_name = f"Structure_rag_{kind}_{model}_chunk{chunk}.yaml"
                new = render(src, model, chunk, kind)
                (BASE_DIR / out_name).write_text(new)
                print(f"  [write] {out_name}")
    # 移除舊的(沒 chunk 後綴) base yaml,避免混淆
    for tpl_name, _ in TEMPLATES:
        old = BASE_DIR / tpl_name
        if old.exists():
            old.unlink()
            print(f"  [remove old] {tpl_name}")
    print(f"\nDone. {len(MODELS) * len(CHUNK_SIZES) * len(TEMPLATES)} yaml files generated.")
    for p in sorted(BASE_DIR.glob("Structure_rag_mem0*.yaml")):
        print(f"  {p.relative_to(BASE_DIR.parent.parent.parent)}")


if __name__ == "__main__":
    main()
