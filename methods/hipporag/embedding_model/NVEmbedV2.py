import os
from copy import deepcopy
from typing import List, Optional

import numpy as np
import torch
from tqdm import tqdm
from transformers import AutoModel

from ..utils.config_utils import BaseConfig
from ..utils.logging_utils import get_logger
from .base import BaseEmbeddingModel, EmbeddingConfig, make_cache_embed

logger = get_logger(__name__)

# Compat shim for transformers ≥ 4.50 (accelerate.infer_auto_device_map):
# newer transformers expects ``PreTrainedModel.all_tied_weights_keys`` (a dict
# mapping group → keys). NV-Embed-v2's custom modeling_nvembed.py predates this
# convention, so AutoModel.from_pretrained crashes inside
# ``_get_device_map → infer_auto_device_map``. We add an empty default at the
# base class level, which means "no tied-weight groups" — safe for inference.
from transformers.modeling_utils import PreTrainedModel as _PTM
if not hasattr(_PTM, "all_tied_weights_keys"):
    _PTM.all_tied_weights_keys = {}  # noqa


class NVEmbedV2EmbeddingModel(BaseEmbeddingModel):

    def __init__(self, global_config: Optional[BaseConfig] = None, embedding_model_name: Optional[str] = None) -> None:
        super().__init__(global_config=global_config)

        if embedding_model_name is not None:
            self.embedding_model_name = embedding_model_name
            logger.debug(f"Overriding {self.__class__.__name__}'s embedding_model_name with: {self.embedding_model_name}")

        self._init_embedding_config()

        # Initializing the embedding model
        logger.debug(f"Initializing {self.__class__.__name__}'s embedding model with params: {self.embedding_config.model_init_params}")

        self.embedding_model = AutoModel.from_pretrained(**self.embedding_config.model_init_params)
        self.embedding_dim = self.embedding_model.config.hidden_size

    def _init_embedding_config(self) -> None:
        """
        Extract embedding model-specific parameters to init the EmbeddingConfig.
        
        Returns:
            None
        """

        config_dict = {
            "embedding_model_name": self.embedding_model_name,
            "norm": self.global_config.embedding_return_as_normalized,
            # "max_seq_length": self.global_config.embedding_max_seq_len,
            "model_init_params": {
                # "model_name_or_path": self.embedding_model_name2mode_name_or_path[self.embedding_model_name],
                "pretrained_model_name_or_path": self.embedding_model_name,
                "trust_remote_code": True,
                # OPT-IN fp16 via env var (default: upstream fp32 unchanged).
                # Set HIPPORAG_EMBED_FP16=1 to load model in fp16, which reduces
                # GPU baseline from 29 GB (fp32) → 14.6 GB. This is a deliberate
                # experiment to measure fp16 vs fp32 EM delta. Not always safe.
                "torch_dtype": ("float16" if os.environ.get("HIPPORAG_EMBED_FP16")
                                else "float32"),
                'device_map': "auto",  # added this line to use multiple GPUs
                # **kwargs
            },
            "encode_params": {
                "max_length": self.global_config.embedding_max_seq_len,  # 32768 from official example,
                "instruction": "",
                "batch_size": self.global_config.embedding_batch_size,
                "num_workers": 32
            },
        }

        self.embedding_config = EmbeddingConfig.from_dict(config_dict=config_dict)
        logger.debug(f"Init {self.__class__.__name__}'s embedding_config: {self.embedding_config}")

    # def _add_eos(self, texts: List[str]) -> List[str]:
    #     # Adds EOS token to each text
    #     return [text + self.embedding_model.tokenizer.eos_token for text in texts]

    def batch_encode(self, texts: List[str], **kwargs) -> None:
        # PATCHED (2026-05-12): inference-only encoding wrapped in torch.no_grad()
        # context. Previously absent, causing autograd to retain all per-layer
        # activations across batches (because the inner loop appended GPU tensors
        # carrying live grad graphs into `results`). Measured impact on 6k FC:
        #   bs=8 chunks indexing peak 51.24 GB GPU  →  patched expected <20 GB.
        # The 32k FC system-RAM peak 67 GB observed earlier was the same effect.
        # NV-Embed-v2 fp16 forward is deterministic, so outputs are bit-identical
        # to the un-patched version (verified: fact_embeddings L2 = 0.0 across runs).

        if isinstance(texts, str): texts = [texts]

        params = deepcopy(self.embedding_config.encode_params)
        if kwargs: params.update(kwargs)

        if "instruction" in kwargs:
            if kwargs["instruction"] != '':
                params["instruction"] = f"Instruct: {kwargs['instruction']}\nQuery: "
            # del params["instruction"]

        batch_size = params.pop("batch_size", 16)

        logger.debug(f"Calling {self.__class__.__name__} with:\n{params}")
        with torch.no_grad():
            if len(texts) <= batch_size:
                params["prompts"] = texts  # self._add_eos(texts=texts)
                results = self.embedding_model.encode(**params)
            else:
                pbar = tqdm(total=len(texts), desc="Batch Encoding")
                results = []
                for i in range(0, len(texts), batch_size):
                    params["prompts"] = texts[i:i + batch_size]
                    results.append(self.embedding_model.encode(**params))
                    pbar.update(batch_size)
                pbar.close()
                results = torch.cat(results, dim=0)

        if isinstance(results, torch.Tensor):
            results = results.cpu()
            results = results.numpy()
        if self.embedding_config.norm:
            results = (results.T / np.linalg.norm(results, axis=1)).T

        return results
