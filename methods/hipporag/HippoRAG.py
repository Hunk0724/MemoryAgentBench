import json
import os
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Union, Optional, List, Set, Dict, Any, Tuple, Literal
import numpy as np
import importlib
from collections import defaultdict
from transformers import HfArgumentParser
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from igraph import Graph
import igraph as ig
import numpy as np
from collections import defaultdict
import re
import time
from .llm import _get_llm_class, BaseLLM
from .embedding_model import _get_embedding_model_class, BaseEmbeddingModel
from .embedding_store import EmbeddingStore
from .information_extraction import OpenIE
from .evaluation.retrieval_eval import RetrievalRecall
from .evaluation.qa_eval import QAExactMatch, QAF1Score
from .prompts.linking import get_query_instruction
from .prompts.prompt_template_manager import PromptTemplateManager
from .rerank import DSPyFilter
from .utils.misc_utils import *
from .utils.embed_utils import retrieve_knn
from .utils.typing import Triple
from .utils.config_utils import BaseConfig

logger = logging.getLogger(__name__)

class HippoRAG:

    def __init__(self, global_config=None, 
                 save_dir=None, 
                 llm_model_name=None, 
                 llm_base_url=None,
                 llm_api_key=None,
                 embedding_model_name=None,
                 embedding_base_url=None,
                 embedding_api_key=None,
                 ):
        """
        Initializes an instance of the class and its related components.

        Attributes:
            global_config (BaseConfig): The global configuration settings for the instance. An instance
                of BaseConfig is used if no value is provided.
            saving_dir (str): The directory where specific HippoRAG instances will be stored. This defaults
                to `outputs` if no value is provided.
            llm_model (BaseLLM): The language model used for processing based on the global
                configuration settings.
            openie (Union[OpenIE, VLLMOfflineOpenIE]): The Open Information Extraction module
                configured in either online or offline mode based on the global settings.
            graph: The graph instance initialized by the `initialize_graph` method.
            embedding_model (BaseEmbeddingModel): The embedding model associated with the current
                configuration.
            chunk_embedding_store (EmbeddingStore): The embedding store handling chunk embeddings.
            entity_embedding_store (EmbeddingStore): The embedding store handling entity embeddings.
            fact_embedding_store (EmbeddingStore): The embedding store handling fact embeddings.
            prompt_template_manager (PromptTemplateManager): The manager for handling prompt templates
                and roles mappings.
            openie_results_path (str): The file path for storing Open Information Extraction results
                based on the dataset and LLM name in the global configuration.
            rerank_filter (Optional[DSPyFilter]): The filter responsible for reranking information
                when a rerank file path is specified in the global configuration.
            ready_to_retrieve (bool): A flag indicating whether the system is ready for retrieval
                operations.

        Parameters:
            global_config: The global configuration object. Defaults to None, leading to initialization
                of a new BaseConfig object.
            working_dir: The directory for storing working files. Defaults to None, constructing a default
                directory based on the class name and timestamp.
            llm_model_name: LLM model name, can be inserted directly as well as through configuration file.
            embedding_model_name: Embedding model name, can be inserted directly as well as through configuration file.
            llm_base_url: LLM URL for a deployed LLM model, can be inserted directly as well as through configuration file.
        """
        if global_config is None:
            self.global_config = BaseConfig()
        else:
            self.global_config = global_config

        #Overwriting Configuration if Specified
        if save_dir is not None:
            self.global_config.save_dir = save_dir

        if llm_model_name is not None:
            self.global_config.llm_name = llm_model_name

        if embedding_model_name is not None:
            self.global_config.embedding_model_name = embedding_model_name

        if llm_base_url is not None:
            self.global_config.llm_base_url = llm_base_url

        if llm_api_key is not None:
            self.global_config.llm_api_key = llm_api_key
        
        if embedding_api_key is not None:
            self.global_config.embedding_api_key = embedding_api_key

        if embedding_base_url is not None:
            self.global_config.embedding_base_url = embedding_base_url

        _print_config = ",\n  ".join([f"{k} = {v}" for k, v in asdict(self.global_config).items()])
        logger.debug(f"HippoRAG init with config:\n  {_print_config}\n")

        #LLM and embedding model specific working directories are created under every specified saving directories
        llm_label = self.global_config.llm_name.replace("/", "_")
        embedding_label = self.global_config.embedding_model_name.replace("/", "_")
        self.working_dir = os.path.join(self.global_config.save_dir, f"{llm_label}_{embedding_label}")

        if not os.path.exists(self.working_dir):
            logger.info(f"Creating working directory: {self.working_dir}")
            os.makedirs(self.working_dir, exist_ok=True)

        self.llm_model: BaseLLM = _get_llm_class(self.global_config)

        if self.global_config.openie_mode == 'online':
            self.openie = OpenIE(llm_model=self.llm_model)
        elif self.global_config.openie_mode == 'offline':
            from .information_extraction.openie_vllm_offline import VLLMOfflineOpenIE
            self.openie = VLLMOfflineOpenIE(self.global_config)

        self.graph = self.initialize_graph()

        if self.global_config.openie_mode == 'offline':
            self.embedding_model = None
        else:
            self.embedding_model: BaseEmbeddingModel = _get_embedding_model_class(
                embedding_model_name=self.global_config.embedding_model_name)(global_config=self.global_config,
                                                                              embedding_model_name=self.global_config.embedding_model_name)
        self.chunk_embedding_store = EmbeddingStore(self.embedding_model,
                                                    os.path.join(self.working_dir, "chunk_embeddings"),
                                                    self.global_config.embedding_batch_size, 'chunk')
        self.entity_embedding_store = EmbeddingStore(self.embedding_model,
                                                     os.path.join(self.working_dir, "entity_embeddings"),
                                                     self.global_config.embedding_batch_size, 'entity')
        self.fact_embedding_store = EmbeddingStore(self.embedding_model,
                                                   os.path.join(self.working_dir, "fact_embeddings"),
                                                   self.global_config.embedding_batch_size, 'fact')

        self.prompt_template_manager = PromptTemplateManager(role_mapping={"system": "system", "user": "user", "assistant": "assistant"})

        self.openie_results_path = os.path.join(self.global_config.save_dir,f'openie_results_ner_{self.global_config.llm_name.replace("/", "_")}.json')

        self.rerank_filter = DSPyFilter(self)

        self.ready_to_retrieve = False

        self.start_time = time.time()

        # ===== v1 Phase 1: Conflict-Aware Fact Annotation =====
        # Added 2026-05-12. method_v1_spec.md §3 Phase 1.
        # Two dicts populated by _phase1_scan_supersession() when enable_supersession=True.
        # superseded_facts: fact_key -> {by_fact_key, observed_chunk_idx, superseder_chunk_idx, s, r, o_old, o_new}
        # chunk_to_fact_keys: chunk_key -> [fact_key, ...]  (for Phase 2 passage→fact reverse lookup)
        self.superseded_facts: Dict[str, Dict] = {}
        self.chunk_to_fact_keys: Dict[str, List[str]] = {}
        self.supersession_index_path = os.path.join(self.working_dir, "supersession_index.json")
        self._load_supersession_index()  # idempotent: loads if file exists, else no-op

        # ===== G.11 Phase 2 per-event dump (env-gated, no-op when unset) =====
        # When HIPPORAG_PHASE2_DUMP_PATH=<jsonl> is set, _phase2_filter_chain_old
        # appends one JSON line per query call with full top-N candidate state for
        # offline P/Q/R-P1/R-P2/S quadrant analysis (G.11 diagnostic).
        self._phase2_dump_path: Optional[str] = os.environ.get("HIPPORAG_PHASE2_DUMP_PATH")
        self._phase2_query_counter: int = 0
        if self._phase2_dump_path:
            # Truncate at init so each run produces a fresh file (no cross-run merge).
            os.makedirs(os.path.dirname(self._phase2_dump_path) or ".", exist_ok=True)
            open(self._phase2_dump_path, "w").close()
            logger.info(f"[G.11] Phase 2 dump enabled → {self._phase2_dump_path}")

        # ===== v2 LLM-judge detector (env-gated, no-op when enable_v2_detect=False) =====
        # Added 2026-05-14. Query-time semantic detection on top-N passage facts.
        # Lazy-init: detector built on first call to graph_search (needs chunk_to_fact_keys
        # populated by index()).
        self._v2_detector = None
        self._v2_chunk_key_to_idx: Dict[str, int] = {}  # chunk_key -> chunk_idx (seq)
        self._v2_last_annotation: str = ""  # per-query, set during retrieve, read during qa
        self._v2_query_to_annotation: Dict[str, str] = {}  # query_text -> annotation
        self._v2_dump_path: Optional[str] = os.environ.get("HIPPORAG_V2_DUMP_PATH")
        if self._v2_dump_path:
            os.makedirs(os.path.dirname(self._v2_dump_path) or ".", exist_ok=True)
            open(self._v2_dump_path, "w").close()
            logger.info(f"[v2] Detection dump enabled → {self._v2_dump_path}")

    def initialize_graph(self):
        """
        Initializes a graph using a GraphML file if available or creates a new graph.

        The function attempts to load a pre-existing graph stored in a GraphML file. If the file
        is not present or the graph needs to be created from scratch, it initializes a new directed
        or undirected graph based on the global configuration. If the graph is loaded successfully
        from the file, pertinent information about the graph (number of nodes and edges) is logged.

        Returns:
            ig.Graph: A pre-loaded or newly initialized graph.

        Raises:
            None
        """
        self._graphml_xml_file = os.path.join(
            self.working_dir, f"graph.graphml"
        )

        preloaded_graph = None

        if not self.global_config.force_index_from_scratch:
            if os.path.exists(self._graphml_xml_file):
                preloaded_graph = ig.Graph.Read_GraphML(self._graphml_xml_file)

        if preloaded_graph is None:
            return ig.Graph(directed=self.global_config.is_directed_graph)
        else:
            logger.info(
                f"Loaded graph from {self._graphml_xml_file} with {preloaded_graph.vcount()} nodes, {preloaded_graph.ecount()} edges"
            )
            return preloaded_graph

    def pre_openie(self,  docs: List[str]):
        logger.info(f"Indexing Documents")
        logger.info(f"Performing OpenIE Offline")

        chunks = self.chunk_embedding_store.get_missing_string_hash_ids(docs)

        all_openie_info, chunk_keys_to_process = self.load_existing_openie(chunks.keys())
        new_openie_rows = {k : chunks[k] for k in chunk_keys_to_process}

        if len(chunk_keys_to_process) > 0:
            new_ner_results_dict, new_triple_results_dict = self.openie.batch_openie(new_openie_rows)
            self.merge_openie_results(all_openie_info, new_openie_rows, new_ner_results_dict, new_triple_results_dict)

        if self.global_config.save_openie:
            self.save_openie_results(all_openie_info)

        assert False, logger.info('Done with OpenIE, run online indexing for future retrieval.')

    # TODO: chunking time
    def index(self, docs: List[str]):
        """
        Indexes the given documents based on the HippoRAG 2 framework which generates an OpenIE knowledge graph
        based on the given documents and encodes passages, entities and facts separately for later retrieval.

        Parameters:
            docs : List[str]
                A list of documents to be indexed.
        """

        logger.info(f"Indexing Documents")

        logger.info(f"Performing OpenIE")

        if self.global_config.openie_mode == 'offline':
            self.pre_openie(docs)

        self.chunk_embedding_store.insert_strings(docs)
        chunks = self.chunk_embedding_store.get_text_for_all_rows()

        all_openie_info, chunk_keys_to_process = self.load_existing_openie(chunks.keys())
        new_openie_rows = {k : chunks[k] for k in chunk_keys_to_process}
        nv_chunking_time_len = time.time() - self.start_time

        if len(chunk_keys_to_process) > 0:
            new_ner_results_dict, new_triple_results_dict = self.openie.batch_openie(new_openie_rows)
            self.merge_openie_results(all_openie_info, new_openie_rows, new_ner_results_dict, new_triple_results_dict)

        if self.global_config.save_openie:
            self.save_openie_results(all_openie_info)

        ner_results_dict, triple_results_dict = reformat_openie_results(all_openie_info)

        assert len(chunks) == len(ner_results_dict) == len(triple_results_dict)
        
        # prepare data_store
        chunk_ids = list(chunks.keys())

        chunk_triples = [[text_processing(t) for t in triple_results_dict[chunk_id].triples] for chunk_id in chunk_ids]
        entity_nodes, chunk_triple_entities = extract_entity_nodes(chunk_triples)
        facts = flatten_facts(chunk_triples)

        logger.info(f"Encoding Entities")
        self.entity_embedding_store.insert_strings(entity_nodes)

        logger.info(f"Encoding Facts")
        self.fact_embedding_store.insert_strings([str(fact) for fact in facts])

        logger.info(f"Constructing Graph")

        self.node_to_node_stats = {}
        self.ent_node_to_num_chunk = {}

        self.add_fact_edges(chunk_ids, chunk_triples)
        num_new_chunks = self.add_passage_edges(chunk_ids, chunk_triple_entities)

        # ===== Build chunk_to_fact_keys mapping (always, regardless of Phase 1) =====
        # Needed by Phase 2 filter (v1) and v2 LLM judge detector.
        # Cheap to build; deterministic from OpenIE triples.
        self._build_chunk_to_fact_keys(chunk_ids, chunk_triples)

        # ===== v1 Phase 1: Conflict-Aware Fact Annotation =====
        # Hook here (after KG edges built, before synonymy KNN). Reads chunk_triples
        # (already in scope), writes self.superseded_facts.
        # Persisted to supersession_index.json next to graph.graphml.
        # Behavior preserved when enable_supersession=False (no-op).
        if getattr(self.global_config, 'enable_supersession', False):
            self._phase1_scan_supersession(chunk_ids, chunk_triples)
            self._save_supersession_index()

        if num_new_chunks > 0:
            logger.info(f"Found {num_new_chunks} new chunks to save into graph.")
            self.add_synonymy_edges()

            self.augment_graph()
            self.save_igraph()

        return nv_chunking_time_len
    
    
    def retrieve(self,
                 queries: List[str],
                 num_to_retrieve: int = None,
                 gold_docs: List[List[str]] = None) -> List[QuerySolution] | Tuple[List[QuerySolution], Dict]:
        """
        Performs retrieval using the HippoRAG 2 framework, which consists of several steps:
        - Fact Retrieval
        - Recognition Memory for improved fact selection
        - Dense passage scoring
        - Personalized PageRank based re-ranking

        Parameters:
            queries: List[str]
                A list of query strings for which documents are to be retrieved.
            num_to_retrieve: int, optional
                The maximum number of documents to retrieve for each query. If not specified, defaults to
                the `retrieval_top_k` value defined in the global configuration.
            gold_docs: List[List[str]], optional
                A list of lists containing gold-standard documents corresponding to each query. Required
                if retrieval performance evaluation is enabled (`do_eval_retrieval` in global configuration).

        Returns:
            List[QuerySolution] or (List[QuerySolution], Dict)
                If retrieval performance evaluation is not enabled, returns a list of QuerySolution objects, each containing
                the retrieved documents and their scores for the corresponding query. If evaluation is enabled, also returns
                a dictionary containing the evaluation metrics computed over the retrieved results.

        Notes
        -----
        - Long queries with no relevant facts after reranking will default to results from dense passage retrieval.
        """

        if num_to_retrieve is None:
            num_to_retrieve = self.global_config.retrieval_top_k

        if gold_docs is not None:
            retrieval_recall_evaluator = RetrievalRecall(global_config=self.global_config)

        if not self.ready_to_retrieve:
            self.prepare_retrieval_objects()

        self.get_query_embeddings(queries)

        retrieval_results = []
        for q_idx, query in tqdm(enumerate(queries), desc="Retrieving", total=len(queries)):
            # new code for retrieval query
            import re
            match = re.search(r"Now Answer the Question:\s*(.*)", query, re.DOTALL)
            if match:
                retrieval_query =  ''.join(match.groups())
            else:
                match = re.search(r"Here is the conversation:\s*(.*)", query, re.DOTALL)
                if match:
                    retrieval_query =  ''.join(match.groups())
                else:
                    retrieval_query = query
            print(f"\n\n\ !!! Retrieve query: {retrieval_query}")
            # end 
            query_fact_scores = self.get_fact_scores(retrieval_query)
            top_k_fact_indices, top_k_facts, rerank_log = self.rerank_facts(retrieval_query, query_fact_scores)

            if len(top_k_facts) == 0:
                logger.info('No facts found after reranking, return DPR results')
                sorted_doc_ids, sorted_doc_scores = self.dense_passage_retrieval(retrieval_query)
            else:
                sorted_doc_ids, sorted_doc_scores = self.graph_search_with_fact_entities(query=retrieval_query,
                                                                                         link_top_k=self.global_config.linking_top_k,
                                                                                         query_fact_scores=query_fact_scores,
                                                                                         top_k_facts=top_k_facts,
                                                                                         top_k_fact_indices=top_k_fact_indices,
                                                                                         passage_node_weight=self.global_config.passage_node_weight)

            top_k_docs = [self.chunk_embedding_store.get_row(self.passage_node_keys[idx])["content"] for idx in sorted_doc_ids[:num_to_retrieve]]

            # v2: align annotation key — graph_search uses retrieval_query, but
            # qa() looks up by full query. Copy under full key.
            if getattr(self.global_config, 'enable_v2_detect', False):
                self._v2_query_to_annotation[query] = self._v2_last_annotation

            retrieval_results.append(QuerySolution(question=query, docs=top_k_docs, doc_scores=sorted_doc_scores[:num_to_retrieve]))

        # Evaluate retrieval
        if gold_docs is not None:
            k_list = [1, 2, 5, 10, 20, 30, 50, 100, 150, 200]
            overall_retrieval_result, example_retrieval_results = retrieval_recall_evaluator.calculate_metric_scores(gold_docs=gold_docs, retrieved_docs=[retrieval_result.docs for retrieval_result in retrieval_results], k_list=k_list)
            logger.info(f"Evaluation results for retrieval: {overall_retrieval_result}")

            return retrieval_results, overall_retrieval_result
        else:
            return retrieval_results, top_k_docs

    def rag_qa(self,
               queries: List[str|QuerySolution],
               gold_docs: List[List[str]] = None,
               gold_answers: List[List[str]] = None) -> Tuple[List[QuerySolution], List[str], List[Dict]] | Tuple[List[QuerySolution], List[str], List[Dict], Dict, Dict]:
        """
        Performs retrieval-augmented generation enhanced QA using the HippoRAG 2 framework.

        This method can handle both string-based queries and pre-processed QuerySolution objects. Depending
        on its inputs, it returns answers only or additionally evaluate retrieval and answer quality using
        recall @ k, exact match and F1 score metrics.

        Parameters:
            queries (List[Union[str, QuerySolution]]): A list of queries, which can be either strings or
                QuerySolution instances. If they are strings, retrieval will be performed.
            gold_docs (Optional[List[List[str]]]): A list of lists containing gold-standard documents for
                each query. This is used if document-level evaluation is to be performed. Default is None.
            gold_answers (Optional[List[List[str]]]): A list of lists containing gold-standard answers for
                each query. Required if evaluation of question answering (QA) answers is enabled. Default
                is None.

        Returns:
            Union[
                Tuple[List[QuerySolution], List[str], List[Dict]],
                Tuple[List[QuerySolution], List[str], List[Dict], Dict, Dict]
            ]: A tuple that always includes:
                - List of QuerySolution objects containing answers and metadata for each query.
                - List of response messages for the provided queries.
                - List of metadata dictionaries for each query.
                If evaluation is enabled, the tuple also includes:
                - A dictionary with overall results from the retrieval phase (if applicable).
                - A dictionary with overall QA evaluation metrics (exact match and F1 scores).

        """
        if gold_answers is not None:
            qa_em_evaluator = QAExactMatch(global_config=self.global_config)
            qa_f1_evaluator = QAF1Score(global_config=self.global_config)

        # Retrieving (if necessary)
        overall_retrieval_result = None

        if not isinstance(queries[0], QuerySolution):
            if gold_docs is not None:
                queries, overall_retrieval_result = self.retrieve(queries=queries, gold_docs=gold_docs)
            else:
                queries = self.retrieve(queries=queries)

        # Performing QA
        queries_solutions, all_response_message, all_metadata = self.qa(queries)

        # Evaluating QA
        if gold_answers is not None:
            overall_qa_em_result, example_qa_em_results = qa_em_evaluator.calculate_metric_scores(
                gold_answers=gold_answers, predicted_answers=[qa_result.answer for qa_result in queries_solutions],
                aggregation_fn=np.max)
            overall_qa_f1_result, example_qa_f1_results = qa_f1_evaluator.calculate_metric_scores(
                gold_answers=gold_answers, predicted_answers=[qa_result.answer for qa_result in queries_solutions],
                aggregation_fn=np.max)

            # round off to 4 decimal places for QA results
            overall_qa_em_result.update(overall_qa_f1_result)
            overall_qa_results = overall_qa_em_result
            overall_qa_results = {k: round(float(v), 4) for k, v in overall_qa_results.items()}
            logger.info(f"Evaluation results for QA: {overall_qa_results}")

            # Save retrieval and QA results
            for idx, q in enumerate(queries_solutions):
                q.gold_answers = list(gold_answers[idx])
                if gold_docs is not None:
                    q.gold_docs = gold_docs[idx]

            return queries_solutions, all_response_message, all_metadata, overall_retrieval_result, overall_qa_results
        else:
            return queries_solutions, all_response_message, all_metadata

    # ===== v1 Phase 3: Universal Reasoning Scaffold =====
    # 2026-05-12. method_v1_spec.md §3 Phase 3.
    # Universal (no conflict / supersedence / seq references) → safe for non-KU tasks.
    # Conditional on "when the answer requires connecting multiple facts" so
    # single-hop questions skip naturally.
    _PHASE3_SCAFFOLD_TEXT = (
        "When the answer requires connecting multiple facts, briefly list "
        "the intermediate entities or facts you use, and ensure that any "
        "entity appearing in multiple steps is referenced consistently."
    )

    def qa(self, queries: List[QuerySolution]) -> Tuple[List[QuerySolution], List[str], List[Dict]]:
        """
        Executes question-answering (QA) inference using a provided set of query solutions and a language model.

        Parameters:
            queries: List[QuerySolution]
                A list of QuerySolution objects that contain the user queries, retrieved documents, and other related information.

        Returns:
            Tuple[List[QuerySolution], List[str], List[Dict]]
                A tuple containing:
                - A list of updated QuerySolution objects with the predicted answers embedded in them.
                - A list of raw response messages from the language model.
                - A list of metadata dictionaries associated with the results.
        """
        #Running inference for QA
        all_qa_messages = []

        for query_solution in tqdm(queries, desc="Collecting QA prompts"):

            # obtain the retrieved docs
            retrieved_passages = query_solution.docs[:self.global_config.qa_top_k]

            prompt_user = ''
            for passage in retrieved_passages:
                prompt_user += f'Wikipedia Title: {passage}\n\n'

            # ===== v2 annotation hook (annotate or both mode) =====
            # Append LLM-detected chain_old annotation between passages and question.
            # Keyed by query text (set during graph_search_with_fact_entities).
            v2_mode = getattr(self.global_config, 'v2_mode', 'off')
            if (getattr(self.global_config, 'enable_v2_detect', False)
                    and v2_mode in ('annotate', 'both')):
                ann = self._v2_query_to_annotation.get(query_solution.question, "")
                if ann:
                    prompt_user += ann + '\n\n'

            # ===== Phase 3 hook: append scaffold before the question =====
            # Placed AFTER passages and BEFORE "Question:" line so it acts as an
            # instruction parsable by the LLM as guidance, not as additional context.
            if getattr(self.global_config, 'enable_phase3_scaffold', False):
                prompt_user += self._PHASE3_SCAFFOLD_TEXT + '\n\n'

            prompt_user += 'Question: ' + query_solution.question + '\nThought: '

            if self.prompt_template_manager.is_template_name_valid(name=f'rag_qa_{self.global_config.dataset}'):
                # find the corresponding prompt for this dataset
                prompt_dataset_name = self.global_config.dataset
            else:
                # the dataset does not have a customized prompt template yet
                logger.debug(
                    f"rag_qa_{self.global_config.dataset} does not have a customized prompt template. Using MUSIQUE's prompt template instead.")
                prompt_dataset_name = 'musique'
            all_qa_messages.append(
                self.prompt_template_manager.render(name=f'rag_qa_{prompt_dataset_name}', prompt_user=prompt_user))

        all_qa_results = [self.llm_model.infer(qa_messages) for qa_messages in tqdm(all_qa_messages, desc="QA Reading")]

        all_response_message, all_metadata, all_cache_hit = zip(*all_qa_results)
        all_response_message, all_metadata = list(all_response_message), list(all_metadata)

        #Process responses and extract predicted answers.
        queries_solutions = []
        for query_solution_idx, query_solution in tqdm(enumerate(queries), desc="Extraction Answers from LLM Response"):
            response_content = all_response_message[query_solution_idx]
            try:
                pred_ans = response_content.split('Answer:')[1].strip()
            except Exception as e:
                logger.warning(f"Error in parsing the answer from the raw LLM QA inference response: {str(e)}!")
                pred_ans = response_content

            query_solution.answer = pred_ans
            queries_solutions.append(query_solution)

        return queries_solutions, all_response_message, all_metadata

    def add_fact_edges(self, chunk_ids: List[str], chunk_triples: List[Tuple]):
        """
        Adds fact edges from given triples to the graph.

        The method processes chunks of triples, computes unique identifiers
        for entities and relations, and updates various internal statistics
        to build and maintain the graph structure. Entities are uniquely
        identified and linked based on their relationships.

        Parameters:
            chunk_ids: List[str]
                A list of unique identifiers for the chunks being processed.
            chunk_triples: List[Tuple]
                A list of tuples representing triples to process. Each triple
                consists of a subject, predicate, and object.

        Raises:
            Does not explicitly raise exceptions within the provided function logic.
        """

        if "name" in self.graph.vs:
            current_graph_nodes = set(self.graph.vs["name"])
        else:
            current_graph_nodes = set()

        logger.info(f"Adding OpenIE triples to graph.")

        for chunk_key, triples in tqdm(zip(chunk_ids, chunk_triples)):
            entities_in_chunk = set()

            if chunk_key not in current_graph_nodes:
                for triple in triples:
                    triple = tuple(triple)
                    fact_key = compute_mdhash_id(content=str(triple), prefix=("fact-"))

                    node_key = compute_mdhash_id(content=triple[0], prefix=("entity-"))
                    node_2_key = compute_mdhash_id(content=triple[2], prefix=("entity-"))

                    self.node_to_node_stats[(node_key, node_2_key)] = self.node_to_node_stats.get(
                        (node_key, node_2_key), 0.0) + 1
                    self.node_to_node_stats[(node_2_key, node_key)] = self.node_to_node_stats.get(
                        (node_2_key, node_key), 0.0) + 1

                    entities_in_chunk.add(node_key)
                    entities_in_chunk.add(node_2_key)

                for node in entities_in_chunk:
                    self.ent_node_to_num_chunk[node] = self.ent_node_to_num_chunk.get(node, 0) + 1

    def add_passage_edges(self, chunk_ids: List[str], chunk_triple_entities: List[List[str]]):
        """
        Adds edges connecting passage nodes to phrase nodes in the graph.

        This method is responsible for iterating through a list of chunk identifiers
        and their corresponding triple entities. It calculates and adds new edges
        between the passage nodes (defined by the chunk identifiers) and the phrase
        nodes (defined by the computed unique hash IDs of triple entities). The method
        also updates the node-to-node statistics map and keeps count of newly added
        passage nodes.

        Parameters:
            chunk_ids : List[str]
                A list of identifiers representing passage nodes in the graph.
            chunk_triple_entities : List[List[str]]
                A list of lists where each sublist contains entities (strings) associated
                with the corresponding chunk in the chunk_ids list.

        Returns:
            int
                The number of new passage nodes added to the graph.
        """

        if "name" in self.graph.vs.attribute_names():
            current_graph_nodes = set(self.graph.vs["name"])
        else:
            current_graph_nodes = set()

        num_new_chunks = 0

        logger.info(f"Connecting passage nodes to phrase nodes.")

        for idx, chunk_key in tqdm(enumerate(chunk_ids)):

            if chunk_key not in current_graph_nodes:
                for chunk_ent in chunk_triple_entities[idx]:
                    node_key = compute_mdhash_id(chunk_ent, prefix="entity-")

                    self.node_to_node_stats[(chunk_key, node_key)] = 1.0

                num_new_chunks += 1

        return num_new_chunks

    def add_synonymy_edges(self):
        """
        Adds synonymy edges between similar nodes in the graph to enhance connectivity by identifying and linking synonym entities.

        This method performs key operations to compute and add synonymy edges. It first retrieves embeddings for all nodes, then conducts
        a nearest neighbor (KNN) search to find similar nodes. These similar nodes are identified based on a score threshold, and edges
        are added to represent the synonym relationship.

        Attributes:
            entity_id_to_row: dict (populated within the function). Maps each entity ID to its corresponding row data, where rows
                              contain `content` of entities used for comparison.
            entity_embedding_store: Manages retrieval of texts and embeddings for all rows related to entities.
            global_config: Configuration object that defines parameters such as `synonymy_edge_topk`, `synonymy_edge_sim_threshold`,
                           `synonymy_edge_query_batch_size`, and `synonymy_edge_key_batch_size`.
            node_to_node_stats: dict. Stores scores for edges between nodes representing their relationship.

        """
        logger.info(f"Expanding graph with synonymy edges")

        self.entity_id_to_row = self.entity_embedding_store.get_text_for_all_rows()
        entity_node_keys = list(self.entity_id_to_row.keys())

        logger.info(f"Performing KNN retrieval for each phrase nodes ({len(entity_node_keys)}).")

        entity_embs = self.entity_embedding_store.get_embeddings(entity_node_keys)

        # Here we build synonymy edges only between newly inserted phrase nodes and all phrase nodes in the storage to reduce cost for incremental graph updates
        query_node_key2knn_node_keys = retrieve_knn(query_ids=entity_node_keys,
                                                    key_ids=entity_node_keys,
                                                    query_vecs=entity_embs,
                                                    key_vecs=entity_embs,
                                                    k=self.global_config.synonymy_edge_topk,
                                                    query_batch_size=self.global_config.synonymy_edge_query_batch_size,
                                                    key_batch_size=self.global_config.synonymy_edge_key_batch_size)

        num_synonym_triple = 0
        synonym_candidates = []  # [(node key, [(synonym node key, corresponding score), ...]), ...]

        for node_key in tqdm(query_node_key2knn_node_keys.keys(), total=len(query_node_key2knn_node_keys)):
            synonyms = []

            entity = self.entity_id_to_row[node_key]["content"]

            if len(re.sub('[^A-Za-z0-9]', '', entity)) > 2:
                nns = query_node_key2knn_node_keys[node_key]

                num_nns = 0
                for nn, score in zip(nns[0], nns[1]):
                    if score < self.global_config.synonymy_edge_sim_threshold or num_nns > 100:
                        break

                    nn_phrase = self.entity_id_to_row[nn]["content"]

                    if nn != node_key and nn_phrase != '':
                        sim_edge = (node_key, nn)
                        synonyms.append((nn, score))
                        num_synonym_triple += 1

                        self.node_to_node_stats[sim_edge] = score  # Need to seriously discuss on this
                        num_nns += 1

            synonym_candidates.append((node_key, synonyms))

    def load_existing_openie(self, chunk_keys: List[str]) -> Tuple[List[dict], Set[str]]:
        """
        Loads existing OpenIE results from the specified file if it exists and combines
        them with new content while standardizing indices. If the file does not exist or
        is configured to be re-initialized from scratch with the flag `force_openie_from_scratch`,
        it prepares new entries for processing.

        Args:
            chunk_keys (List[str]): A list of chunk keys that represent identifiers
                                     for the content to be processed.

        Returns:
            Tuple[List[dict], Set[str]]: A tuple where the first element is the existing OpenIE
                                         information (if any) loaded from the file, and the
                                         second element is a set of chunk keys that still need to
                                         be saved or processed.
        """

        # combine openie_results with contents already in file, if file exists
        chunk_keys_to_save = set()

        if not self.global_config.force_openie_from_scratch and os.path.isfile(self.openie_results_path):
            openie_results = json.load(open(self.openie_results_path))
            all_openie_info = openie_results.get('docs', [])

            #Standardizing indices for OpenIE Files.

            renamed_openie_info = []
            for openie_info in all_openie_info:
                openie_info['idx'] = compute_mdhash_id(openie_info['passage'], 'chunk-')
                renamed_openie_info.append(openie_info)

            all_openie_info = renamed_openie_info

            existing_openie_keys = set([info['idx'] for info in all_openie_info])

            for chunk_key in chunk_keys:
                if chunk_key not in existing_openie_keys:
                    chunk_keys_to_save.add(chunk_key)
        else:
            all_openie_info = []
            chunk_keys_to_save = chunk_keys

        return all_openie_info, chunk_keys_to_save

    def merge_openie_results(self,
                             all_openie_info: List[dict],
                             chunks_to_save: Dict[str, dict],
                             ner_results_dict: Dict[str, NerRawOutput],
                             triple_results_dict: Dict[str, TripleRawOutput]) -> List[dict]:
        """
        Merges OpenIE extraction results with corresponding passage and metadata.

        This function integrates the OpenIE extraction results, including named-entity
        recognition (NER) entities and triples, with their respective text passages
        using the provided chunk keys. The resulting merged data is appended to
        the `all_openie_info` list containing dictionaries with combined and organized
        data for further processing or storage.

        Parameters:
            all_openie_info (List[dict]): A list to hold dictionaries of merged OpenIE
                results and metadata for all chunks.
            chunks_to_save (Dict[str, dict]): A dict of chunk identifiers (keys) to process
                and merge OpenIE results to dictionaries with `hash_id` and `content` keys.
            ner_results_dict (Dict[str, NerRawOutput]): A dictionary mapping chunk keys
                to their corresponding NER extraction results.
            triple_results_dict (Dict[str, TripleRawOutput]): A dictionary mapping chunk
                keys to their corresponding OpenIE triple extraction results.

        Returns:
            List[dict]: The `all_openie_info` list containing dictionaries with merged
            OpenIE results, metadata, and the passage content for each chunk.

        """

        for chunk_key, row in chunks_to_save.items():
            passage = row['content']
            chunk_openie_info = {'idx': chunk_key, 'passage': passage,
                                 'extracted_entities': ner_results_dict[chunk_key].unique_entities,
                                 'extracted_triples': triple_results_dict[chunk_key].triples}
            all_openie_info.append(chunk_openie_info)

        return all_openie_info

    def save_openie_results(self, all_openie_info: List[dict]):
        """
        Computes statistics on extracted entities from OpenIE results and saves the aggregated data in a
        JSON file. The function calculates the average character and word lengths of the extracted entities
        and writes them along with the provided OpenIE information to a file.

        Parameters:
            all_openie_info : List[dict]
                List of dictionaries, where each dictionary represents information from OpenIE, including
                extracted entities.
        """

        sum_phrase_chars = sum([len(e) for chunk in all_openie_info for e in chunk['extracted_entities']])
        sum_phrase_words = sum([len(e.split()) for chunk in all_openie_info for e in chunk['extracted_entities']])
        num_phrases = sum([len(chunk['extracted_entities']) for chunk in all_openie_info])

        if len(all_openie_info) > 0:
            openie_dict = {'docs': all_openie_info, 'avg_ent_chars': round(sum_phrase_chars / num_phrases, 4),
                           'avg_ent_words': round(sum_phrase_words / num_phrases, 4)}
            with open(self.openie_results_path, 'w') as f:
                json.dump(openie_dict, f)
            logger.info(f"OpenIE results saved to {self.openie_results_path}")

    def augment_graph(self):
        """
        Provides utility functions to augment a graph by adding new nodes and edges.
        It ensures that the graph structure is extended to include additional components,
        and logs the completion status along with printing the updated graph information.
        """

        self.add_new_nodes()
        self.add_new_edges()

        logger.info(f"Graph construction completed!")
        print(self.get_graph_info())

    # ============================================================================
    # v1 Phase 1: Conflict-Aware Fact Annotation
    # Added 2026-05-12. See method_v1_spec.md §3 Phase 1 + claude_chat...md §B.7.1
    #
    # Detection rule: group all OpenIE triples by (subject.lower(), relation.lower()).
    # Any (S, R) bucket with >1 distinct object → conflict candidate. Latest chunk's
    # objects are 'active', objects from earlier chunks marked superseded at fact_key
    # level (NOT graph-edge level — graph edges collapse relation; see chat §B.7.1).
    # ============================================================================
    def _build_chunk_to_fact_keys(self, chunk_ids: List[str], chunk_triples: List[List[Tuple]]):
        """Always-built mapping: chunk_key -> [fact_key, ...].

        Decoupled from Phase 1 so v2 LLM judge can use it without requiring
        enable_supersession=True. Deterministic from OpenIE chunk_triples.
        """
        self.chunk_to_fact_keys = {}
        for chunk_idx, (chunk_key, triples) in enumerate(zip(chunk_ids, chunk_triples)):
            self.chunk_to_fact_keys.setdefault(chunk_key, [])
            for triple in triples:
                if not (isinstance(triple, (list, tuple)) and len(triple) == 3):
                    continue
                s, r, o = [str(x).strip() for x in triple]
                if not s or not r or not o:
                    continue
                fact_key = compute_mdhash_id(content=str(tuple(triple)), prefix="fact-")
                self.chunk_to_fact_keys[chunk_key].append(fact_key)

    def _phase1_scan_supersession(self, chunk_ids: List[str], chunk_triples: List[List[Tuple]]):
        """Scan chunk_triples for same-(S,R)-different-O conflicts; mark earlier fact_keys
        as superseded.

        Populates:
          self.superseded_facts[fact_key] = {by_fact_key, observed_chunk_idx,
                                              superseder_chunk_idx, s, r, o_old, o_new}

        Assumes self.chunk_to_fact_keys already populated by _build_chunk_to_fact_keys.
        Idempotent: clears existing superseded_facts state first.
        """
        # Reset prior state (e.g., when re-indexing same corpus)
        self.superseded_facts = {}

        # Group all facts by (s_norm, r_norm)
        sr_to_occurrences = defaultdict(list)
        # Each occurrence: (chunk_idx_int, chunk_key, o_str_orig, fact_key)

        for chunk_idx, (chunk_key, triples) in enumerate(zip(chunk_ids, chunk_triples)):
            for triple in triples:
                if not (isinstance(triple, (list, tuple)) and len(triple) == 3):
                    continue
                s, r, o = [str(x).strip() for x in triple]
                if not s or not r or not o:
                    continue
                fact_key = compute_mdhash_id(content=str(tuple(triple)), prefix="fact-")
                sr_to_occurrences[(s.lower(), r.lower())].append(
                    (chunk_idx, chunk_key, o, fact_key)
                )

        # For each (S, R) bucket with multiple distinct objects, mark earlier as superseded.
        # Tie-breaking: latest chunk_idx wins; if multiple facts in latest chunk share (S,R)
        # but different O, all of them are 'active' (rare, but possible).
        n_conflicts = 0
        for (s_low, r_low), occurrences in sr_to_occurrences.items():
            # Get unique (object, fact_key) pairs across occurrences
            distinct_o = {(o, fk) for _, _, o, fk in occurrences}
            if len({o for o, _ in distinct_o}) <= 1:
                continue  # All same object, no conflict

            latest_chunk_idx = max(idx for idx, _, _, _ in occurrences)
            latest_fact_keys = {fk for idx, _, _, fk in occurrences if idx == latest_chunk_idx}
            latest_objects = {o for idx, _, o, _ in occurrences if idx == latest_chunk_idx}

            for idx, chunk_key, o, fk in occurrences:
                # Skip facts that ARE in the latest chunk (they're active)
                if fk in latest_fact_keys:
                    continue
                # Already marked (handle duplicate fact_key across chunks)
                if fk in self.superseded_facts:
                    continue
                self.superseded_facts[fk] = {
                    "by_fact_key": next(iter(latest_fact_keys)),
                    "observed_chunk_idx": idx,
                    "observed_chunk_key": chunk_key,
                    "superseder_chunk_idx": latest_chunk_idx,
                    "s": s_low,
                    "r": r_low,
                    "o_old": o,
                    "o_new": next(iter(latest_objects)),
                }
                n_conflicts += 1

        logger.info(
            f"[Phase 1] scanned {sum(len(v) for v in self.chunk_to_fact_keys.values())} facts "
            f"across {len(self.chunk_to_fact_keys)} chunks; "
            f"detected {n_conflicts} superseded fact_keys "
            f"({len([(s, r) for (s, r), occs in sr_to_occurrences.items() if len({o for _, _, o, _ in occs}) > 1])} conflict (S,R) buckets)"
        )

    def _save_supersession_index(self):
        """Persist superseded_facts + chunk_to_fact_keys to JSON."""
        payload = {
            "version": 1,
            "schema_note": "v1 Phase 1 supersession index. fact_key -> {by_fact_key, observed_chunk_idx, "
                           "superseder_chunk_idx, s, r, o_old, o_new}. chunk_to_fact_keys: chunk_key -> [fact_key,...]",
            "superseded_facts": self.superseded_facts,
            "chunk_to_fact_keys": self.chunk_to_fact_keys,
            "n_superseded": len(self.superseded_facts),
            "n_chunks": len(self.chunk_to_fact_keys),
        }
        os.makedirs(os.path.dirname(self.supersession_index_path), exist_ok=True)
        with open(self.supersession_index_path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"[Phase 1] saved supersession index to {self.supersession_index_path} "
                    f"({len(self.superseded_facts)} superseded facts)")

    def _load_supersession_index(self):
        """Load supersession index from JSON if file exists. Safe no-op otherwise."""
        if not os.path.exists(self.supersession_index_path):
            return
        try:
            with open(self.supersession_index_path) as f:
                payload = json.load(f)
            self.superseded_facts = payload.get("superseded_facts", {})
            self.chunk_to_fact_keys = payload.get("chunk_to_fact_keys", {})
            logger.info(f"[Phase 1] loaded supersession index from {self.supersession_index_path} "
                        f"({len(self.superseded_facts)} superseded facts)")
        except Exception as e:
            logger.warning(f"[Phase 1] failed to load supersession index ({e}), starting fresh")
            self.superseded_facts = {}
            self.chunk_to_fact_keys = {}

    # ============================================================================
    # v1 Phase 2: Chain-Aware Passage Filtering
    # Added 2026-05-12. See method_v1_spec.md §3 Phase 2.
    #
    # Rule: among top-N PPR-ranked passages, filter any passage whose constituent
    # superseded facts have BOTH endpoints (s, o_old) in the top-X% PPR-mass
    # phrase set. "Both endpoints high mass" ≈ "this superseded fact is on the
    # current query's reasoning chain" (proxy: query-aware filter, not
    # query-agnostic delete).
    #
    # Depends on Phase 1 metadata (self.superseded_facts + chunk_to_fact_keys).
    # ============================================================================
    def _phase2_filter_chain_old(self,
                                 sorted_doc_ids: np.ndarray,
                                 sorted_doc_scores: np.ndarray,
                                 pagerank_scores: np.ndarray,
                                 top_n: int = 20):
        """Filter passages whose superseded constituent facts have both endpoints
        in high-mass phrase set.

        Args:
            sorted_doc_ids: indices into self.passage_node_idxs (passage rank, length N_passages)
            sorted_doc_scores: parallel PPR doc scores
            pagerank_scores: full PPR mass array (length=#graph_vertices)
            top_n: only examine top-N ranked passages (avoid scanning long tail)

        Returns:
            (filtered_sorted_doc_ids, filtered_sorted_doc_scores) — same dtype/shape as inputs
            (just possibly shorter if some passages dropped)
        """
        if not self.superseded_facts or not self.chunk_to_fact_keys:
            logger.debug("[Phase 2] no supersession metadata available, skip filter")
            return sorted_doc_ids, sorted_doc_scores

        # 1. Compute high-mass phrase set: top-X% by PPR mass over phrase (entity) nodes only
        percentile = getattr(self.global_config, "phase2_high_mass_percentile", 80.0)
        # entity_node_idxs are graph vertex indices of phrase nodes
        entity_pagerank = np.array([pagerank_scores[v] for v in self.entity_node_idxs])
        if len(entity_pagerank) == 0:
            return sorted_doc_ids, sorted_doc_scores
        threshold = float(np.percentile(entity_pagerank, percentile))
        # vertex-idx set: graph vertices with PPR mass >= threshold, restricted to phrase nodes
        high_mass_vertex_idxs = {
            self.entity_node_idxs[i]
            for i, score in enumerate(entity_pagerank)
            if score >= threshold
        }

        # 2. Iterate top-N passages and check for triggered superseded facts
        keep_mask = np.ones(len(sorted_doc_ids), dtype=bool)
        n_filtered = 0
        filter_events = []
        dump_candidates = []  # G.11: per-passage state for offline P/Q/R analysis
        actual_top_n = min(top_n, len(sorted_doc_ids))
        for rank in range(actual_top_n):
            passage_doc_idx = int(sorted_doc_ids[rank])
            chunk_key = self.passage_node_keys[passage_doc_idx]
            fact_keys = self.chunk_to_fact_keys.get(chunk_key, [])
            cand_record = {
                "rank": rank, "chunk_key": chunk_key,
                "ppr_score": float(sorted_doc_scores[rank]),
                "n_fact_keys": len(fact_keys),
                "superseded_fact_details": [],  # all superseded facts inside this passage
                "filter_triggered": False, "filter_trigger_fact_key": None,
            }
            if not fact_keys:
                dump_candidates.append(cand_record)
                continue
            for fk in fact_keys:
                if fk not in self.superseded_facts:
                    continue
                sf = self.superseded_facts[fk]
                s_entity_key = compute_mdhash_id(content=sf["s"], prefix="entity-")
                o_old_entity_key = compute_mdhash_id(content=sf["o_old"], prefix="entity-")
                s_vertex_idx = self.node_name_to_vertex_idx.get(s_entity_key)
                o_old_vertex_idx = self.node_name_to_vertex_idx.get(o_old_entity_key)
                endpoints_in_high_mass = (
                    s_vertex_idx is not None and o_old_vertex_idx is not None
                    and s_vertex_idx in high_mass_vertex_idxs
                    and o_old_vertex_idx in high_mass_vertex_idxs
                )
                cand_record["superseded_fact_details"].append({
                    "fact_key": fk, "s": sf["s"], "r": sf["r"],
                    "o_old": sf["o_old"], "o_new": sf["o_new"],
                    "s_in_high_mass": s_vertex_idx is not None and s_vertex_idx in high_mass_vertex_idxs,
                    "o_old_in_high_mass": o_old_vertex_idx is not None and o_old_vertex_idx in high_mass_vertex_idxs,
                })
                if endpoints_in_high_mass and not cand_record["filter_triggered"]:
                    keep_mask[rank] = False
                    n_filtered += 1
                    cand_record["filter_triggered"] = True
                    cand_record["filter_trigger_fact_key"] = fk
                    filter_events.append({
                        "rank": rank, "chunk_key": chunk_key, "trigger_fact_key": fk,
                        "s": sf["s"], "r": sf["r"], "o_old": sf["o_old"], "o_new": sf["o_new"],
                    })
                    # Don't break: continue scanning so dump_candidates records ALL
                    # superseded facts in this passage (for full diagnostic visibility).
            dump_candidates.append(cand_record)

        if n_filtered > 0:
            logger.info(
                f"[Phase 2] filtered {n_filtered} passages in top-{actual_top_n} "
                f"(threshold={threshold:.4f} @ p{percentile}, "
                f"high_mass_entities={len(high_mass_vertex_idxs)}/{len(self.entity_node_idxs)})"
            )
            # Store last filter events on self for inspection (optional, low cost)
            self._last_phase2_filter_events = filter_events

        # G.11: dump per-query state if env var set (no-op otherwise)
        if self._phase2_dump_path:
            try:
                with open(self._phase2_dump_path, "a") as f:
                    json.dump({
                        "q_idx": self._phase2_query_counter,
                        "percentile": percentile,
                        "threshold": threshold,
                        "n_high_mass_entities": len(high_mass_vertex_idxs),
                        "n_total_entities": len(self.entity_node_idxs),
                        "actual_top_n": actual_top_n,
                        "n_filtered": n_filtered,
                        "candidates": dump_candidates,
                    }, f)
                    f.write("\n")
            except Exception as e:
                logger.warning(f"[G.11] dump write failed: {e}")
            self._phase2_query_counter += 1

        return sorted_doc_ids[keep_mask], sorted_doc_scores[keep_mask]

    def _ensure_v2_detector(self):
        """Lazy-init the v2 LLMJudgeDetector. Requires chunk_to_fact_keys populated."""
        if self._v2_detector is not None:
            return
        from .v2_llm_judge import LLMJudgeDetector
        # Build chunk_key -> chunk_idx (seq) by iterating passage nodes in order
        if not self._v2_chunk_key_to_idx:
            for idx, ck in enumerate(self.passage_node_keys):
                self._v2_chunk_key_to_idx[ck] = idx
        # Build fact_key -> content map from fact_embedding_store
        fact_rows = self.fact_embedding_store.get_text_for_all_rows()
        fact_content_map = {fk: row["content"] for fk, row in fact_rows.items()}
        self._v2_detector = LLMJudgeDetector(
            llm_model=self.llm_model,
            chunk_to_fact_keys=self.chunk_to_fact_keys,
            fact_content_map=fact_content_map,
            chunk_key_to_idx=self._v2_chunk_key_to_idx,
        )
        logger.info(f"[v2] LLMJudgeDetector ready "
                    f"(n_chunks={len(self.chunk_to_fact_keys)}, n_facts={len(fact_content_map)})")

    def _v2_llm_judge_apply(self, query: str, sorted_doc_ids: np.ndarray,
                             sorted_doc_scores: np.ndarray,
                             query_fact_scores: Optional[np.ndarray] = None):
        """v2 detection: run LLM judge on top-N passages, then filter and/or
        store annotation per global_config.v2_mode.

        Args:
            query_fact_scores: optional precomputed cosine scores between query
                and each fact (indexed by self.fact_node_keys). Enables top-K
                fact pre-filter via global_config.v2_top_k_facts.
        """
        v2_mode = getattr(self.global_config, 'v2_mode', 'off')
        if v2_mode == 'off':
            return sorted_doc_ids, sorted_doc_scores
        if not self.chunk_to_fact_keys:
            logger.debug("[v2] no chunk_to_fact_keys (was indexing skipped?), skip detection")
            return sorted_doc_ids, sorted_doc_scores
        self._ensure_v2_detector()

        top_n = getattr(self.global_config, 'v2_top_n_passages', 20)
        actual_top_n = min(top_n, len(sorted_doc_ids))
        top_n_chunk_keys = [self.passage_node_keys[int(sorted_doc_ids[r])]
                            for r in range(actual_top_n)]

        # Build fact_key → query cosine score map (for optional top-K pre-filter)
        fact_key_to_score = None
        top_k_facts = getattr(self.global_config, 'v2_top_k_facts', None)
        if top_k_facts is not None and query_fact_scores is not None:
            try:
                # query_fact_scores is indexed by fact_node_keys
                fact_key_to_score = dict(zip(self.fact_node_keys, query_fact_scores))
            except Exception as e:
                logger.warning(f"[v2] failed to build fact_key→score map: {e}")
                fact_key_to_score = None

        result = self._v2_detector.detect(query, top_n_chunk_keys,
                                          fact_key_to_query_score=fact_key_to_score,
                                          top_k_facts=top_k_facts)
        chain_old_chunk_keys = result["chain_old_chunk_keys"]
        annotation_text = result["annotation_text"]

        # Store annotation for qa() (keyed by query text)
        self._v2_query_to_annotation[query] = annotation_text
        self._v2_last_annotation = annotation_text

        # Dump per-query state if env var set
        if self._v2_dump_path:
            try:
                with open(self._v2_dump_path, "a") as f:
                    json.dump({
                        "query": query, "v2_mode": v2_mode,
                        "actual_top_n": actual_top_n,
                        "n_facts_sent": result["n_facts_sent"],
                        "n_chain_old_fact_keys": len(result["chain_old_fact_keys"]),
                        "n_chain_old_chunk_keys": len(chain_old_chunk_keys),
                        "conflict_groups": [
                            [{"seq": s, "fact_key": fk} for s, fk in grp]
                            for grp in result["conflict_groups"]
                        ],
                        "chain_old_chunk_keys": sorted(chain_old_chunk_keys),
                        "annotation_text": annotation_text,
                    }, f)
                    f.write("\n")
            except Exception as e:
                logger.warning(f"[v2] dump write failed: {e}")

        # Filter mode: drop passages whose chunk_key is in chain_old set
        if v2_mode in ('filter', 'both') and chain_old_chunk_keys:
            keep_mask = np.ones(len(sorted_doc_ids), dtype=bool)
            n_filtered = 0
            for rank in range(actual_top_n):
                ck = self.passage_node_keys[int(sorted_doc_ids[rank])]
                if ck in chain_old_chunk_keys:
                    keep_mask[rank] = False
                    n_filtered += 1
            if n_filtered > 0:
                logger.info(
                    f"[v2] mode={v2_mode}: filtered {n_filtered} passages "
                    f"from top-{actual_top_n} (chain_old detected by LLM judge)"
                )
            return sorted_doc_ids[keep_mask], sorted_doc_scores[keep_mask]

        return sorted_doc_ids, sorted_doc_scores

    def add_new_nodes(self):
        """
        Adds new nodes to the graph from entity and passage embedding stores based on their attributes.

        This method identifies and adds new nodes to the graph by comparing existing nodes
        in the graph and nodes retrieved from the entity embedding store and the passage
        embedding store. The method checks attributes and ensures no duplicates are added.
        New nodes are prepared and added in bulk to optimize graph updates.
        """

        existing_nodes = {v["name"]: v for v in self.graph.vs if "name" in v.attributes()}

        entity_nodes = self.entity_embedding_store.get_text_for_all_rows()
        passage_nodes = self.chunk_embedding_store.get_text_for_all_rows()

        nodes = entity_nodes
        nodes.update(passage_nodes)

        new_nodes = {}
        for node_id, node in nodes.items():
            node['name'] = node_id
            if node_id not in existing_nodes:
                for k, v in node.items():
                    if k not in new_nodes:
                        new_nodes[k] = []
                    new_nodes[k].append(v)

        if len(new_nodes) > 0:
            self.graph.add_vertices(n=len(next(iter(new_nodes.values()))), attributes=new_nodes)

    def add_new_edges(self):
        """
        Processes edges from `node_to_node_stats` to add them into a graph object while
        managing adjacency lists, validating edges, and logging invalid edge cases.
        """

        graph_adj_list = defaultdict(dict)
        graph_inverse_adj_list = defaultdict(dict)
        edge_source_node_keys = []
        edge_target_node_keys = []
        edge_metadata = []
        for edge, weight in self.node_to_node_stats.items():
            if edge[0] == edge[1]: continue
            graph_adj_list[edge[0]][edge[1]] = weight
            graph_inverse_adj_list[edge[1]][edge[0]] = weight

            edge_source_node_keys.append(edge[0])
            edge_target_node_keys.append(edge[1])
            edge_metadata.append({
                "weight": weight
            })

        valid_edges, valid_weights = [], {"weight": []}
        current_node_ids = set(self.graph.vs["name"])
        for source_node_id, target_node_id, edge_d in zip(edge_source_node_keys, edge_target_node_keys, edge_metadata):
            if source_node_id in current_node_ids and target_node_id in current_node_ids:
                valid_edges.append((source_node_id, target_node_id))
                weight = edge_d.get("weight", 1.0)
                valid_weights["weight"].append(weight)
            else:
                logger.warning(f"Edge {source_node_id} -> {target_node_id} is not valid.")
        self.graph.add_edges(
            valid_edges,
            attributes=valid_weights
        )

    def save_igraph(self):
        logger.info(
            f"Writing graph with {len(self.graph.vs())} nodes, {len(self.graph.es())} edges"
        )
        self.graph.write_graphml(self._graphml_xml_file)
        logger.info(f"Saving graph completed!")

    def get_graph_info(self) -> Dict:
        """
        Obtains detailed information about the graph such as the number of nodes,
        triples, and their classifications.

        This method calculates various statistics about the graph based on the
        stores and node-to-node relationships, including counts of phrase and
        passage nodes, total nodes, extracted triples, triples involving passage
        nodes, synonymy triples, and total triples.

        Returns:
            Dict
                A dictionary containing the following keys and their respective values:
                - num_phrase_nodes: The number of unique phrase nodes.
                - num_passage_nodes: The number of unique passage nodes.
                - num_total_nodes: The total number of nodes (sum of phrase and passage nodes).
                - num_extracted_triples: The number of unique extracted triples.
                - num_triples_with_passage_node: The number of triples involving at least one
                  passage node.
                - num_synonymy_triples: The number of synonymy triples (distinct from extracted
                  triples and those with passage nodes).
                - num_total_triples: The total number of triples.
        """
        graph_info = {}

        # get # of phrase nodes
        phrase_nodes_keys = self.entity_embedding_store.get_all_ids()
        graph_info["num_phrase_nodes"] = len(set(phrase_nodes_keys))

        # get # of passage nodes
        passage_nodes_keys = self.chunk_embedding_store.get_all_ids()
        graph_info["num_passage_nodes"] = len(set(passage_nodes_keys))

        # get # of total nodes
        graph_info["num_total_nodes"] = graph_info["num_phrase_nodes"] + graph_info["num_passage_nodes"]

        # get # of extracted triples
        graph_info["num_extracted_triples"] = len(self.fact_embedding_store.get_all_ids())

        num_triples_with_passage_node = 0
        passage_nodes_set = set(passage_nodes_keys)
        num_triples_with_passage_node = sum(
            1 for node_pair in self.node_to_node_stats
            if node_pair[0] in passage_nodes_set or node_pair[1] in passage_nodes_set
        )
        graph_info['num_triples_with_passage_node'] = num_triples_with_passage_node

        graph_info['num_synonymy_triples'] = len(self.node_to_node_stats) - graph_info[
            "num_extracted_triples"] - num_triples_with_passage_node

        # get # of total triples
        graph_info["num_total_triples"] = len(self.node_to_node_stats)

        return graph_info

    def prepare_retrieval_objects(self):
        """
        Prepares various in-memory objects and attributes necessary for fast retrieval processes, such as embedding data and graph relationships, ensuring consistency
        and alignment with the underlying graph structure.
        """

        logger.info("Preparing for fast retrieval.")

        logger.info("Loading keys.")
        self.query_to_embedding: Dict = {'triple': {}, 'passage': {}}

        self.entity_node_keys: List = list(self.entity_embedding_store.get_all_ids()) # a list of phrase node keys
        self.passage_node_keys: List = list(self.chunk_embedding_store.get_all_ids()) # a list of passage node keys
        self.fact_node_keys: List = list(self.fact_embedding_store.get_all_ids())

        assert len(self.entity_node_keys) + len(self.passage_node_keys) == self.graph.vcount()

        igraph_name_to_idx = {node["name"]: idx for idx, node in enumerate(self.graph.vs)} # from node key to the index in the backbone graph
        self.node_name_to_vertex_idx = igraph_name_to_idx
        self.entity_node_idxs = [igraph_name_to_idx[node_key] for node_key in self.entity_node_keys] # a list of backbone graph node index
        self.passage_node_idxs = [igraph_name_to_idx[node_key] for node_key in self.passage_node_keys] # a list of backbone passage node index

        logger.info("Loading embeddings.")
        self.entity_embeddings = np.array(self.entity_embedding_store.get_embeddings(self.entity_node_keys))
        self.passage_embeddings = np.array(self.chunk_embedding_store.get_embeddings(self.passage_node_keys))

        self.fact_embeddings = np.array(self.fact_embedding_store.get_embeddings(self.fact_node_keys))

        self.ready_to_retrieve = True

    def get_query_embeddings(self, queries: List[str] | List[QuerySolution]):
        """
        Retrieves embeddings for given queries and updates the internal query-to-embedding mapping. The method determines whether each query
        is already present in the `self.query_to_embedding` dictionary under the keys 'triple' and 'passage'. If a query is not present in
        either, it is encoded into embeddings using the embedding model and stored.

        Args:
            queries List[str] | List[QuerySolution]: A list of query strings or QuerySolution objects. Each query is checked for
            its presence in the query-to-embedding mappings.
        """

        all_query_strings = []
        for query in queries:
            if isinstance(query, QuerySolution) and (
                    query.question not in self.query_to_embedding['triple'] or query.question not in
                    self.query_to_embedding['passage']):
                all_query_strings.append(query.question)
            elif query not in self.query_to_embedding['triple'] or query not in self.query_to_embedding['passage']:
                all_query_strings.append(query)

        if len(all_query_strings) > 0:
            # get all query embeddings
            logger.info(f"Encoding {len(all_query_strings)} queries for query_to_fact.")
            query_embeddings_for_triple = self.embedding_model.batch_encode(all_query_strings,
                                                                            instruction=get_query_instruction('query_to_fact'),
                                                                            norm=True)
            for query, embedding in zip(all_query_strings, query_embeddings_for_triple):
                self.query_to_embedding['triple'][query] = embedding

            logger.info(f"Encoding {len(all_query_strings)} queries for query_to_passage.")
            query_embeddings_for_passage = self.embedding_model.batch_encode(all_query_strings,
                                                                             instruction=get_query_instruction('query_to_passage'),
                                                                             norm=True)
            for query, embedding in zip(all_query_strings, query_embeddings_for_passage):
                self.query_to_embedding['passage'][query] = embedding

    def get_fact_scores(self, query: str) -> np.ndarray:
        """
        Retrieves and computes normalized similarity scores between the given query and pre-stored fact embeddings.

        Parameters:
        query : str
            The input query text for which similarity scores with fact embeddings
            need to be computed.

        Returns:
        numpy.ndarray
            A normalized array of similarity scores between the query and fact
            embeddings. The shape of the array is determined by the number of
            facts.

        Raises:
        KeyError
            If no embedding is found for the provided query in the stored query
            embeddings dictionary.
        """
        query_embedding = self.query_to_embedding['triple'].get(query, None)
        if query_embedding is None:
            query_embedding = self.embedding_model.batch_encode(query,
                                                                instruction=get_query_instruction('query_to_fact'),
                                                                norm=True)

        query_fact_scores = np.dot(self.fact_embeddings, query_embedding.T) # shape: (#facts, )
        query_fact_scores = np.squeeze(query_fact_scores) if query_fact_scores.ndim == 2 else query_fact_scores
        query_fact_scores = min_max_normalize(query_fact_scores)

        return query_fact_scores

    def dense_passage_retrieval(self, query: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Conduct dense passage retrieval to find relevant documents for a query.

        This function processes a given query using a pre-trained embedding model
        to generate query embeddings. The similarity scores between the query
        embedding and passage embeddings are computed using dot product, followed
        by score normalization. Finally, the function ranks the documents based
        on their similarity scores and returns the ranked document identifiers
        and their scores.

        Parameters
        ----------
        query : str
            The input query for which relevant passages should be retrieved.

        Returns
        -------
        tuple : Tuple[np.ndarray, np.ndarray]
            A tuple containing two elements:
            - A list of sorted document identifiers based on their relevance scores.
            - A numpy array of the normalized similarity scores for the corresponding
              documents.
        """
        query_embedding = self.query_to_embedding['passage'].get(query, None)
        if query_embedding is None:
            query_embedding = self.embedding_model.batch_encode(query,
                                                                instruction=get_query_instruction('query_to_passage'),
                                                                norm=True)
        query_doc_scores = np.dot(self.passage_embeddings, query_embedding.T)
        query_doc_scores = np.squeeze(query_doc_scores) if query_doc_scores.ndim == 2 else query_doc_scores
        query_doc_scores = min_max_normalize(query_doc_scores)

        sorted_doc_ids = np.argsort(query_doc_scores)[::-1]
        sorted_doc_scores = query_doc_scores[sorted_doc_ids.tolist()]
        return sorted_doc_ids, sorted_doc_scores


    def get_top_k_weights(self,
                          link_top_k: int,
                          all_phrase_weights: np.ndarray,
                          linking_score_map: Dict[str, float]) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        This function filters the all_phrase_weights to retain only the weights for the
        top-ranked phrases in terms of the linking_score_map. It also filters linking scores
        to retain only the top `link_top_k` ranked nodes. Non-selected phrases in phrase
        weights are reset to a weight of 0.0.

        Args:
            link_top_k (int): Number of top-ranked nodes to retain in the linking score map.
            all_phrase_weights (np.ndarray): An array representing the phrase weights, indexed
                by phrase ID.
            linking_score_map (Dict[str, float]): A mapping of phrase content to its linking
                score, sorted in descending order of scores.

        Returns:
            Tuple[np.ndarray, Dict[str, float]]: A tuple containing the filtered array
            of all_phrase_weights with unselected weights set to 0.0, and the filtered
            linking_score_map containing only the top `link_top_k` phrases.
        """
        # choose top ranked nodes in linking_score_map
        linking_score_map = dict(sorted(linking_score_map.items(), key=lambda x: x[1], reverse=True)[:link_top_k])

        # only keep the top_k phrases in all_phrase_weights
        top_k_phrases = set(linking_score_map.keys())
        top_k_phrases_keys = set(
            [compute_mdhash_id(content=top_k_phrase, prefix="entity-") for top_k_phrase in top_k_phrases])

        for phrase_key in self.node_name_to_vertex_idx:
            if phrase_key not in top_k_phrases_keys:
                phrase_id = self.node_name_to_vertex_idx.get(phrase_key, None)
                if phrase_id is not None:
                    all_phrase_weights[phrase_id] = 0.0

        assert np.count_nonzero(all_phrase_weights) == len(linking_score_map.keys())
        return all_phrase_weights, linking_score_map

    def graph_search_with_fact_entities(self, query: str,
                                        link_top_k: int,
                                        query_fact_scores: np.ndarray,
                                        top_k_facts: List[Tuple],
                                        top_k_fact_indices: List[str],
                                        passage_node_weight: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes document scores based on fact-based similarity and relevance using personalized
        PageRank (PPR) and dense retrieval models. This function combines the signal from the relevant
        facts identified with passage similarity and graph-based search for enhanced result ranking.

        Parameters:
            query (str): The input query string for which similarity and relevance computations
                need to be performed.
            link_top_k (int): The number of top phrases to include from the linking score map for
                downstream processing.
            query_fact_scores (np.ndarray): An array of scores representing fact-query similarity
                for each of the provided facts.
            top_k_facts (List[Tuple]): A list of top-ranked facts, where each fact is represented
                as a tuple of its subject, predicate, and object.
            top_k_fact_indices (List[str]): Corresponding indices or identifiers for the top-ranked
                facts in the query_fact_scores array.
            passage_node_weight (float): Default weight to scale passage scores in the graph.

        Returns:
            Tuple[np.ndarray, np.ndarray]: A tuple containing two arrays:
                - The first array corresponds to document IDs sorted based on their scores.
                - The second array consists of the PPR scores associated with the sorted document IDs.
        """
        #Assigning phrase weights based on selected facts from previous steps.
        linking_score_map = {}  # from phrase to the average scores of the facts that contain the phrase
        phrase_scores = {}  # store all fact scores for each phrase regardless of whether they exist in the knowledge graph or not
        phrase_weights = np.zeros(len(self.graph.vs['name']))
        passage_weights = np.zeros(len(self.graph.vs['name']))

        for rank, f in enumerate(top_k_facts):
            subject_phrase = f[0].lower()
            predicate_phrase = f[1].lower()
            object_phrase = f[2].lower()
            fact_score = query_fact_scores[
                top_k_fact_indices[rank]] if query_fact_scores.ndim > 0 else query_fact_scores
            for phrase in [subject_phrase, object_phrase]:
                phrase_key = compute_mdhash_id(
                    content=phrase,
                    prefix="entity-"
                )
                phrase_id = self.node_name_to_vertex_idx.get(phrase_key, None)

                if phrase_id is not None:
                    phrase_weights[phrase_id] = fact_score

                    if self.ent_node_to_num_chunk[phrase_key] != 0:
                        phrase_weights[phrase_id] /= self.ent_node_to_num_chunk[phrase_key]

                if phrase not in phrase_scores:
                    phrase_scores[phrase] = []
                phrase_scores[phrase].append(fact_score)

        # calculate average fact score for each phrase
        for phrase, scores in phrase_scores.items():
            linking_score_map[phrase] = float(np.mean(scores))

        if link_top_k:
            phrase_weights, linking_score_map = self.get_top_k_weights(link_top_k,
                                                                           phrase_weights,
                                                                           linking_score_map)  # at this stage, the length of linking_scope_map is determined by link_top_k

        #Get passage scores according to chosen dense retrieval model
        dpr_sorted_doc_ids, dpr_sorted_doc_scores = self.dense_passage_retrieval(query)
        normalized_dpr_sorted_scores = min_max_normalize(dpr_sorted_doc_scores)

        for i, dpr_sorted_doc_id in enumerate(dpr_sorted_doc_ids.tolist()):
            passage_node_key = self.passage_node_keys[dpr_sorted_doc_id]
            passage_dpr_score = normalized_dpr_sorted_scores[i]
            passage_node_id = self.node_name_to_vertex_idx[passage_node_key]
            passage_weights[passage_node_id] = passage_dpr_score * passage_node_weight
            passage_node_text = self.chunk_embedding_store.get_row(passage_node_key)["content"]
            linking_score_map[passage_node_text] = passage_dpr_score * passage_node_weight

        #Combining phrase and passage scores into one array for PPR
        node_weights = phrase_weights + passage_weights

        #Recording top 30 facts in linking_score_map
        if len(linking_score_map) > 30:
            linking_score_map = dict(sorted(linking_score_map.items(), key=lambda x: x[1], reverse=True)[:30])

        assert sum(node_weights) > 0, f'No phrases found in the graph for the given facts: {top_k_facts}'

        #Running PPR algorithm based on the passage and phrase weights previously assigned
        ppr_sorted_doc_ids, ppr_sorted_doc_scores, pagerank_scores = self.run_ppr(node_weights, damping=self.global_config.damping)

        assert len(ppr_sorted_doc_ids) == len(
            self.passage_node_idxs), f"Doc prob length {len(ppr_sorted_doc_ids)} != corpus length {len(self.passage_node_idxs)}"

        # ===== v1 Phase 2: Chain-Aware Passage Filtering =====
        # 2026-05-12. method_v1_spec.md §3 Phase 2.
        # Apply AFTER PPR converges (so we have full mass distribution), BEFORE
        # return (so downstream rerank_filter / qa see filtered passages).
        # No-op when enable_phase2_filter=False or supersession_facts empty.
        if getattr(self.global_config, 'enable_phase2_filter', False):
            ppr_sorted_doc_ids, ppr_sorted_doc_scores = self._phase2_filter_chain_old(
                ppr_sorted_doc_ids, ppr_sorted_doc_scores, pagerank_scores
            )

        # ===== v2 LLM judge detection (filter and/or annotate modes) =====
        # 2026-05-14. Query-time LLM judge on top-N passage facts; mechanical
        # seq direction (chunk_idx); filter chain_old passages and/or store
        # annotation text for qa() to read.
        if getattr(self.global_config, 'enable_v2_detect', False):
            ppr_sorted_doc_ids, ppr_sorted_doc_scores = self._v2_llm_judge_apply(
                query, ppr_sorted_doc_ids, ppr_sorted_doc_scores,
                query_fact_scores=query_fact_scores
            )

        return ppr_sorted_doc_ids, ppr_sorted_doc_scores


    def rerank_facts(self, query: str, query_fact_scores: np.ndarray) -> Tuple[List[int], List[Tuple], dict]:
        """

        Args:

        Returns:
            top_k_fact_indicies:
            top_k_facts:
            rerank_log (dict): {'facts_before_rerank': candidate_facts, 'facts_after_rerank': top_k_facts}
                - candidate_facts (list): list of link_top_k facts (each fact is a relation triple in tuple data type).
                - top_k_facts:


        """
        # load args
        link_top_k: int = self.global_config.linking_top_k

        candidate_fact_indices = np.argsort(query_fact_scores)[-link_top_k:][
                                 ::-1].tolist()  # list of ranked link_top_k fact relative indices
        real_candidate_fact_ids = [self.fact_node_keys[idx] for idx in
                                   candidate_fact_indices]  # list of ranked link_top_k fact keys
        fact_row_dict = self.fact_embedding_store.get_rows(real_candidate_fact_ids)
        candidate_facts = [eval(fact_row_dict[id]['content']) for id in real_candidate_fact_ids]  # list of link_top_k facts (each fact is a relation triple in tuple data type)

        top_k_fact_indices, top_k_facts, reranker_dict = self.rerank_filter(query,
                                                                             candidate_facts,
                                                                             candidate_fact_indices,
                                                                             len_after_rerank=link_top_k)

        rerank_log = {'facts_before_rerank': candidate_facts, 'facts_after_rerank': top_k_facts}

        return top_k_fact_indices, top_k_facts, rerank_log
    
    def run_ppr(self,
                reset_prob: np.ndarray,
                damping: float =0.5) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Runs Personalized PageRank (PPR) on a graph and computes relevance scores for
        nodes corresponding to document passages. The method utilizes a damping
        factor for teleportation during rank computation and can take a reset
        probability array to influence the starting state of the computation.

        Parameters:
            reset_prob (np.ndarray): A 1-dimensional array specifying the reset
                probability distribution for each node. The array must have a size
                equal to the number of nodes in the graph. NaNs or negative values
                within the array are replaced with zeros.
            damping (float): A scalar specifying the damping factor for the
                computation. Defaults to 0.5 if not provided or set to `None`.

        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: 3-tuple:
                - sorted_doc_ids: indices into self.passage_node_idxs, ranked desc by PPR mass
                - sorted_doc_scores: PPR scores for the passages in sorted_doc_ids order
                - pagerank_scores: full PPR mass array, length=#graph_nodes (added 2026-05-12
                    for Phase 2 chain-aware filter, which needs phrase node mass distribution
                    to pick high-mass entities). Backward-compat note: existing callers
                    unpacking `(a, b)` will break — update them too.
        """

        if damping is None: damping = 0.5 # for potential compatibility
        reset_prob = np.where(np.isnan(reset_prob) | (reset_prob < 0), 0, reset_prob)
        pagerank_scores = self.graph.personalized_pagerank(
            vertices=range(len(self.node_name_to_vertex_idx)),
            damping=damping,
            directed=False,
            weights='weight',
            reset=reset_prob,
            implementation='prpack'
        )
        pagerank_scores_arr = np.asarray(pagerank_scores)

        doc_scores = np.array([pagerank_scores[idx] for idx in self.passage_node_idxs])
        sorted_doc_ids = np.argsort(doc_scores)[::-1]
        sorted_doc_scores = doc_scores[sorted_doc_ids.tolist()]

        return sorted_doc_ids, sorted_doc_scores, pagerank_scores_arr