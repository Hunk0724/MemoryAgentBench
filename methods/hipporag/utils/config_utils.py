import os
from dataclasses import dataclass, field
from typing import (
    Literal,
    Union,
    Optional
)

from .logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class BaseConfig:
    """One and only configuration."""
    # LLM specific attributes 
    llm_name: str = field(
        default="gpt-4o-mini",
        metadata={"help": "Class name indicating which LLM model to use."}
    )
    llm_base_url: str = field(
        default=None,
        metadata={"help": "Base URL for the LLM model, if none, means using OPENAI service."}
    )
    max_new_tokens: Union[None, int] = field(
        default=2048,
        metadata={"help": "Max new tokens to generate in each inference."}
    )
    num_gen_choices: int = field(
        default=1,
        metadata={"help": "How many chat completion choices to generate for each input message."}
    )
    seed: Union[None, int] = field(
        default=None,
        metadata={"help": "Random seed."}
    )
    temperature: float = field(
        default=0,
        metadata={"help": "Temperature for sampling in each inference."}
    )
    response_format: Union[dict, None] = field(
        default_factory=lambda: { "type": "json_object" },
        metadata={"help": "Specifying the format that the model must output."}
    )
    
    ## LLM specific attributes -> Async hyperparameters
    max_retry_attempts: int = field(
        default=5,
        metadata={"help": "Max number of retry attempts for an asynchronous API calling."}
    )
    # Storage specific attributes
    force_openie_from_scratch: bool = field(
        default=False,
        metadata={"help": "If set to True, will ignore all existing openie files and rebuild them from scratch."}
    )

    # Storage specific attributes 
    force_index_from_scratch: bool = field(
        default=False,
        metadata={"help": "If set to True, will ignore all existing storage files and graph data and will rebuild from scratch."}
    )
    rerank_dspy_file_path: str = field(
        default=None,
        metadata={"help": "Path to the rerank dspy file."}
    )
    passage_node_weight: float = field(
        default=0.05,
        metadata={"help": "Multiplicative factor that modified the passage node weights in PPR."}
    )
    save_openie: bool = field(
        default=True,
        metadata={"help": "If set to True, will save the OpenIE model to disk."}
    )
    
    # Preprocessing specific attributes
    text_preprocessor_class_name: str = field(
        default="TextPreprocessor",
        metadata={"help": "Name of the text-based preprocessor to use in preprocessing."}
    )
    preprocess_encoder_name: str = field(
        default="gpt-4o",
        metadata={"help": "Name of the encoder to use in preprocessing (currently implemented specifically for doc chunking)."}
    )
    preprocess_chunk_overlap_token_size: int = field(
        default=128,
        metadata={"help": "Number of overlap tokens between neighbouring chunks."}
    )
    preprocess_chunk_max_token_size: int = field(
        default=None,
        metadata={"help": "Max number of tokens each chunk can contain. If set to None, the whole doc will treated as a single chunk."}
    )
    preprocess_chunk_func: Literal["by_token", "by_word"] = field(default='by_token')
    
    
    # Information extraction specific attributes
    information_extraction_model_name: Literal["openie_openai_gpt", ] = field(
        default="openie_openai_gpt",
        metadata={"help": "Class name indicating which information extraction model to use."}
    )
    openie_mode: Literal["offline", "online"] = field(
        default="online",
        metadata={"help": "Mode of the OpenIE model to use."}
    )
    skip_graph: bool = field(
        default=False,
        metadata={"help": "Whether to skip graph construction or not. Set it to be true when running vllm offline indexing for the first time."}
    )
    
    
    # Embedding specific attributes
    embedding_model_name: str = field(
        default="nvidia/NV-Embed-v2",
        metadata={"help": "Class name indicating which embedding model to use."}
    )
    embedding_batch_size: int = field(
        default_factory=lambda: int(os.environ.get("HIPPORAG_EMBED_BATCH_SIZE", "16")),
        metadata={"help": "Batch size of calling embedding model. "
                          "Default 16 matches upstream MemoryAgentBench (benchmark default). "
                          "Override via env: HIPPORAG_EMBED_BATCH_SIZE=4 bash ... to control GPU peak. "
                          "See docs/hardware_request_6k.md for per-bs measured peaks. "
                          "NV-Embed-v2 fp16 forward is deterministic so bs only affects speed/memory, not output."}
    )
    embedding_return_as_normalized: bool = field(
        default=True,
        metadata={"help": "Whether to normalize encoded embeddings not."}
    )
    embedding_max_seq_len: int = field(
        default=2048,
        metadata={"help": "Max sequence length for the embedding model."}
    )
    
    
    
    # Graph construction specific attributes
    synonymy_edge_topk: int = field(
        default=2047,
        metadata={"help": "k for knn retrieval in buiding synonymy edges."}
    )
    synonymy_edge_query_batch_size: int = field(
        default=1000,
        metadata={"help": "Batch size for query embeddings for knn retrieval in buiding synonymy edges."}
    )
    synonymy_edge_key_batch_size: int = field(
        default=10000,
        metadata={"help": "Batch size for key embeddings for knn retrieval in buiding synonymy edges."}
    )
    synonymy_edge_sim_threshold: float = field(
        default=0.8,
        metadata={"help": "Similarity threshold to include candidate synonymy nodes."}
    )
    is_directed_graph: bool = field(
        default=False,
        metadata={"help": "Whether the graph is directed or not."}
    )

    # ===== v1 conflict mechanism flags (default False = upstream vanilla) =====
    # Added 2026-05-12 for FactConsolidation conflict-aware extension.
    # method_v1_spec.md §4 — Feature flag preservation.
    enable_supersession: bool = field(
        default=False,
        metadata={"help": "Phase 1: scan OpenIE triples for same (S, R) different O conflicts "
                          "and mark earlier fact_keys as superseded. Stores metadata in "
                          "self.superseded_facts dict + self.chunk_to_fact_keys map, "
                          "persisted as supersession_index.json next to graph.graphml. "
                          "Does NOT modify graph structure — vanilla retrieval/PPR unchanged."}
    )
    enable_phase2_filter: bool = field(
        default=False,
        metadata={"help": "Phase 2: query-time chain-aware passage filter. Requires "
                          "enable_supersession=True (depends on Phase 1 metadata)."}
    )
    enable_phase3_scaffold: bool = field(
        default=False,
        metadata={"help": "Phase 3: append universal multi-hop reasoning scaffold to rag_qa system prompt."}
    )
    phase2_high_mass_percentile: float = field(
        default=80.0,
        metadata={"help": "Phase 2: phrase node PPR-mass percentile threshold for 'query-relevant entity' set. "
                          "Default 80.0 = top 20%. Higher = stricter (less filtering)."}
    )

    # ===== v2 LLM-judge detection flags (default off = upstream vanilla) =====
    # Added 2026-05-14 after v1+G.11 pivot. method_v2 design:
    # query-time semantic detection via LLM grouping + mechanical seq direction.
    enable_v2_detect: bool = field(
        default=False,
        metadata={"help": "v2: query-time LLM judge detection on top-N passage facts. "
                          "Replaces (or augments) v1 P1+P2 deterministic detection. "
                          "Uses Wikidata-style functional/cumulative/temporal-functional "
                          "taxonomy in prompt; direction resolved by chunk_idx (=seq)."}
    )
    v2_mode: Literal["filter", "annotate", "both", "off"] = field(
        default="off",
        metadata={"help": "v2 output mode: 'filter' drops chain_old passages (like v1 P2); "
                          "'annotate' keeps passages but appends 'note: facts X are outdated' "
                          "to QA prompt; 'both' applies filter + annotation; 'off' detect-only "
                          "(useful for diagnostic without affecting EM)."}
    )
    v2_top_n_passages: int = field(
        default=20,
        metadata={"help": "v2: how many PPR-ranked passages to extract facts from for LLM judge."}
    )
    v2_top_k_facts: Optional[int] = field(
        default=None,
        metadata={"help": "v2: optional cosine pre-filter cap. When set, only the top-K facts "
                          "by cosine(query, fact_emb) are sent to LLM judge. None = send all "
                          "facts from top-N passages (may overwhelm LLM at large corpus). "
                          "Recommended: 30-50 for FC-MH 6k (where corpus = 449 facts)."}
    )
    v2_llm_temperature: float = field(
        default=0.0,
        metadata={"help": "v2: temperature for LLM judge detector (deterministic by default)."}
    )


    # Retrieval specific attributes
    linking_top_k: int = field(
        default=5,
        metadata={"help": "The number of linked nodes at each retrieval step"}
    )
    retrieval_top_k: int = field(
        default=200,
        metadata={"help": "Retrieving k documents at each step"}
    )
    damping: float = field(
        default=0.5,
        metadata={"help": "Damping factor for ppr algorithm."}
    )
    
    
    # QA specific attributes
    max_qa_steps: int = field(
        default=1,
        metadata={"help": "For answering a single question, the max steps that we use to interleave retrieval and reasoning."}
    )
    qa_top_k: int = field(
        default=5,
        metadata={"help": "Feeding top k documents to the QA model for reading."}
    )
    
    # Save dir (highest level directory)
    save_dir: str = field(
        default=None,
        metadata={"help": "Directory to save all related information. If it's given, will overwrite all default save_dir setups. If it's not given, then if we're not running specific datasets, default to `outputs`, otherwise, default to a dataset-customized output dir."}
    )
    
    
    
    # Dataset running specific attributes
    ## Dataset running specific attributes -> General
    dataset: Optional[Literal['hotpotqa', 'hotpotqa_train', 'musique', '2wikimultihopqa']] = field(
        default=None,
        metadata={"help": "Dataset to use. If specified, it means we will run specific datasets. If not specified, it means we're running freely."}
    )
    ## Dataset running specific attributes -> Graph
    graph_type: Literal[
        'dpr_only', 
        'entity', 
        'passage_entity', 'relation_aware_passage_entity',
        'passage_entity_relation', 
        'facts_and_sim_passage_node_unidirectional',
    ] = field(
        default="facts_and_sim_passage_node_unidirectional",
        metadata={"help": "Type of graph to use in the experiment."}
    )
    corpus_len: Optional[int] = field(
        default=None,
        metadata={"help": "Length of the corpus to use."}
    )
    
    
    def __post_init__(self):
        if self.save_dir is None: # If save_dir not given
            if self.dataset is None: self.save_dir = 'outputs' # running freely
            else: self.save_dir = os.path.join('outputs', self.dataset) # customize your dataset's output dir here
        logger.debug(f"Initializing the highest level of save_dir to be {self.save_dir}")

        # ===== v1 conflict mechanism flags — env var override (2026-05-12) =====
        # Lets us toggle phases from shell without yaml edits:
        #   HIPPORAG_ENABLE_SUPERSESSION=1 bash run_hipporag_gemini.sh
        # Accepted truthy values: "1", "true", "yes" (case-insensitive). Anything else = False.
        # When env var is UNSET, the dataclass default (False) wins → vanilla behavior preserved.
        for flag_attr, env_name in [
            ("enable_supersession", "HIPPORAG_ENABLE_SUPERSESSION"),
            ("enable_phase2_filter", "HIPPORAG_ENABLE_PHASE2_FILTER"),
            ("enable_phase3_scaffold", "HIPPORAG_ENABLE_PHASE3_SCAFFOLD"),
        ]:
            env_val = os.environ.get(env_name)
            if env_val is not None:
                setattr(self, flag_attr, env_val.lower() in ("1", "true", "yes"))
                logger.info(f"[config] env override: {flag_attr} = {getattr(self, flag_attr)} (from {env_name}={env_val!r})")

        # Phase 2 percentile (numeric) — env var override for percentile sweep
        pct_env = os.environ.get("HIPPORAG_PHASE2_PERCENTILE")
        if pct_env is not None:
            try:
                self.phase2_high_mass_percentile = float(pct_env)
                logger.info(f"[config] env override: phase2_high_mass_percentile = {self.phase2_high_mass_percentile} (from HIPPORAG_PHASE2_PERCENTILE={pct_env!r})")
            except ValueError:
                logger.warning(f"[config] HIPPORAG_PHASE2_PERCENTILE={pct_env!r} not a float, ignoring")

        # ===== v2 LLM-judge env overrides (2026-05-14) =====
        v2_detect_env = os.environ.get("HIPPORAG_ENABLE_V2_DETECT")
        if v2_detect_env is not None:
            self.enable_v2_detect = v2_detect_env.lower() in ("1", "true", "yes")
            logger.info(f"[config] env override: enable_v2_detect = {self.enable_v2_detect} (from HIPPORAG_ENABLE_V2_DETECT={v2_detect_env!r})")

        v2_mode_env = os.environ.get("HIPPORAG_V2_MODE")
        if v2_mode_env is not None:
            if v2_mode_env in ("filter", "annotate", "both", "off"):
                self.v2_mode = v2_mode_env
                logger.info(f"[config] env override: v2_mode = {self.v2_mode!r} (from HIPPORAG_V2_MODE={v2_mode_env!r})")
            else:
                logger.warning(f"[config] HIPPORAG_V2_MODE={v2_mode_env!r} not a valid mode, ignoring")

        v2_topn_env = os.environ.get("HIPPORAG_V2_TOP_N_PASSAGES")
        if v2_topn_env is not None:
            try:
                self.v2_top_n_passages = int(v2_topn_env)
                logger.info(f"[config] env override: v2_top_n_passages = {self.v2_top_n_passages} (from HIPPORAG_V2_TOP_N_PASSAGES={v2_topn_env!r})")
            except ValueError:
                logger.warning(f"[config] HIPPORAG_V2_TOP_N_PASSAGES={v2_topn_env!r} not an int, ignoring")

        v2_topk_env = os.environ.get("HIPPORAG_V2_TOP_K_FACTS")
        if v2_topk_env is not None:
            try:
                self.v2_top_k_facts = int(v2_topk_env)
                logger.info(f"[config] env override: v2_top_k_facts = {self.v2_top_k_facts} (from HIPPORAG_V2_TOP_K_FACTS={v2_topk_env!r})")
            except ValueError:
                logger.warning(f"[config] HIPPORAG_V2_TOP_K_FACTS={v2_topk_env!r} not an int, ignoring")