
@inproceedings{wulongmemeval,
  title={LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory},
  author={Wu, Di and Wang, Hongwei and Yu, Wenhao and Zhang, Yuwei and Chang, Kai-Wei and Yu, Dong},
  booktitle={The Thirteenth International Conference on Learning Representations},
  year={2025}
}

@inproceedings{hu2026evaluating,
  title={Evaluating Memory in {LLM} Agents via Incremental Multi-Turn Interactions},
  author={Yuanzhe Hu and Yu Wang and Julian McAuley},
  booktitle={The Fourteenth International Conference on Learning Representations},
  year={2026},
  url={https://openreview.net/forum?id=DT7JyQC3MR}
}

@inproceedings{tavakoli2026beyond,
  title={Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in {LLM}s},
  author={Mohammad Tavakoli and Alireza Salemi and Carrie Ye and Mohamed Abdalla and Hamed Zamani and J Ross Mitchell},
  booktitle={The Fourteenth International Conference on Learning Representations},
  year={2026},
  url={https://openreview.net/forum?id=y59hf5lrMn}
}

@inproceedings{zhong2023mquake,
  title={Mquake: Assessing knowledge editing in language models via multi-hop questions},
  author={Zhong, Zexuan and Wu, Zhengxuan and Manning, Christopher D and Potts, Christopher and Chen, Danqi},
  booktitle={Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing},
  pages={15686--15702},
  year={2023}
}

@article{chhikara2025mem0,
  title={Mem0: Building production-ready ai agents with scalable long-term memory},
  author={Chhikara, Prateek and Khant, Dev and Aryan, Saket and Singh, Taranjeet and Yadav, Deshraj},
  journal={arXiv preprint arXiv:2504.19413},
  year={2025}
}

@inproceedings{
  fang2026lightmem,
  title={LightMem: Lightweight and Efficient Memory-Augmented Generation},
  author={Jizhan Fang and Xinle Deng and Haoming Xu and Ziyan Jiang and Yuqi Tang and Ziwen Xu and Shumin Deng and Yunzhi Yao and Mengru Wang and Shuofei Qiao and Huajun Chen and Ningyu Zhang},
  booktitle={The Fourteenth International Conference on Learning Representations},
  year={2026},
  url={https://openreview.net/forum?id=dyJ0GWpjJB}
}

@article{rasmussen2025zep,
  title={Zep: a temporal knowledge graph architecture for agent memory},
  author={Rasmussen, Preston and Paliychuk, Pavlo and Beauvais, Travis and Ryan, Jack and Chalef, Daniel},
  journal={arXiv preprint arXiv:2501.13956},
  year={2025}
}

@article{wang2026less,
  title={Less Context, More Accuracy: A Bi-Temporal Memory Engine for LLM Agents Where a Lean Retrieved Context Beats the Full History},
  author={Wang, Liuyin},
  journal={arXiv preprint arXiv:2606.09900},
  year={2026}
}

@article{reddy2026don,
  title={Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution},
  author={Reddy, Vikas and Challaram, Sumanth},
  journal={arXiv preprint arXiv:2606.01435},
  year={2026}
}

@inproceedings{longpre2021entity,
  title={Entity-based knowledge conflicts in question answering},
  author={Longpre, Shayne and Perisetla, Kartik and Chen, Anthony and Ramesh, Nikhil and DuBois, Chris and Singh, Sameer},
  booktitle={Proceedings of the 2021 conference on empirical methods in natural language processing},
  pages={7052--7063},
  year={2021}
}

@inproceedings{xu2024knowledge,
  title={Knowledge conflicts for llms: A survey},
  author={Xu, Rongwu and Qi, Zehan and Guo, Zhijiang and Wang, Cunxiang and Wang, Hongru and Zhang, Yue and Xu, Wei},
  booktitle={Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing},
  pages={8541--8565},
  year={2024}
}

@inproceedings{pham2025slimlm,
  title={Slimlm: An efficient small language model for on-device document assistance},
  author={Pham, Thang M and Nguyen, Phat T and Yoon, Seunghyun and Lai, Viet Dac and Dernoncourt, Franck and Bui, Trung},
  booktitle={Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 3: System Demonstrations)},
  pages={436--447},
  year={2025}
}

@article{chenfrugalgpt,
  title={FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance},
  author={Chen, Lingjiao and Zaharia, Matei and Zou, James},
  journal={Transactions on Machine Learning Research},
  year={2024}
}

@inproceedings{wang-etal-2025-astute,
    title = "Astute {RAG}: Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts for Large Language Models",
    author = "Wang, Fei  and
      Wan, Xingchen  and
      Sun, Ruoxi  and
      Chen, Jiefeng  and
      Arik, Sercan O",
    editor = "Che, Wanxiang  and
      Nabende, Joyce  and
      Shutova, Ekaterina  and
      Pilehvar, Mohammad Taher",
    booktitle = "Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)",
    month = jul,
    year = "2025",
    address = "Vienna, Austria",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2025.acl-long.1476/",
    doi = "10.18653/v1/2025.acl-long.1476",
    pages = "30553--30571",
    ISBN = "979-8-89176-251-0",
    abstract = "Retrieval augmented generation (RAG), while effectively integrating external knowledge to address the inherent limitations of large language models (LLMs), can be hindered by imperfect retrieval that contain irrelevant, misleading, or even malicious information. Previous studies have rarely connected the behavior of RAG through joint analysis, particularly regarding error propagation coming from imperfect retrieval and potential conflicts between LLMs' internal knowledge and external sources. Through comprehensive and controlled analyses under realistic conditions, we find that imperfect retrieval augmentation is inevitable, common, and harmful. We identify the knowledge conflicts between LLM-internal and external knowledge from retrieval as a bottleneck to overcome imperfect retrieval in the post-retrieval stage of RAG. To address this, we propose Astute RAG, a novel RAG approach designed to be resilient to imperfect retrieval augmentation. It adaptively elicits essential information from LLMs' internal knowledge, iteratively consolidates internal and external knowledge with source-awareness, and finalizes the answer according to information reliability. Our experiments with Gemini and Claude demonstrate the superior performance of Astute RAG compared to previous robustness-enhanced RAG approaches. Specifically, Astute RAG is the only RAG method that achieves performance comparable to or even surpassing conventional use of LLMs under the worst-case scenario. Further analysis reveals the effectiveness of Astute RAG in resolving knowledge conflicts, thereby improving the trustworthiness of RAG."
}

@inproceedings{liu2026truthfulrag,
  title={Truthfulrag: Resolving factual-level conflicts in retrieval-augmented generation with knowledge graphs},
  author={Liu, Shuyi and Shang, Yu-Ming and Zhang, Xi},
  booktitle={Proceedings of the AAAI Conference on Artificial Intelligence},
  volume={40},
  number={38},
  pages={32168--32176},
  year={2026}
}

@inproceedings{li2025t,
  title={T-grag: A dynamic graphrag framework for resolving temporal conflicts and redundancy in knowledge retrieval},
  author={Li, Dong and Niu, Yichen and Ai, Ying and Zou, Xiang and Qi, Biqing and Liu, Jianxing},
  booktitle={Proceedings of the 33rd ACM International Conference on Multimedia},
  pages={11880--11889},
  year={2025}
}

@article{zhong2023comprehensive,
  title={A comprehensive survey on automatic knowledge graph construction},
  author={Zhong, Lingfeng and Wu, Jia and Li, Qian and Peng, Hao and Wu, Xindong},
  journal={ACM Computing Surveys},
  volume={56},
  number={4},
  pages={1--62},
  year={2023},
  publisher={ACM New York, NY}
}