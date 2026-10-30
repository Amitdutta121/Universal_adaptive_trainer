"""RAG-Anything (LightRAG underneath) on the CS220 hand-labelled retrieval set.

    python run.py index [--limit N]     # LLM entity/relation extraction on every chunk
    python run.py query                 # every retrieval mode, scored against the hand labels

Each of our chunks is inserted as its own document with our chunk id as file_path, so a
retrieved chunk maps straight back to the gold labels. Chunks are under LightRAG's 1200-token
chunk size, so LightRAG does not split them. LLM: Azure gpt-5-mini; embeddings: Azure
text-embedding-3-small (the embedder Grouper uses), so only the retrieval method differs.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from lightrag import QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from raganything import RAGAnything, RAGAnythingConfig

HERE = Path(__file__).parent
ENV = dotenv_values(r"C:\Users\amit\orca\workspaces\FInalAdaptiveTrainer\grouper\.env")
BASE, KEY = ENV["AZURE_BASE_URL"], ENV["AZURE_API_KEY"]
DATA = json.loads((HERE / "input.json").read_text(encoding="utf-8"))
MODES = ["naive", "local", "global", "hybrid", "mix"]
# Optional local cross-encoder as LightRAG's rerank_model_func: RERANKER=minilm|bge-base|bge-m3
RERANKERS = {
    "minilm": "cross-encoder--ms-marco-MiniLM-L-6-v2",
    "bge-base": "BAAI--bge-reranker-base",
    "bge-m3": "BAAI--bge-reranker-v2-m3",
}
RERANKER = __import__("os").environ.get("RERANKER")
_cross = None


_vec_cache = {}


async def embed_large(texts):
    """OpenAI text-embedding-3-large through OpenRouter (not deployed on our Azure)."""
    missing = [t for t in dict.fromkeys(texts) if t not in _vec_cache]
    for i in range(0, len(missing), 64):
        batch = missing[i : i + 64]
        vecs = await openai_embed.func(
            batch,
            model="openai/text-embedding-3-large",
            base_url="https://openrouter.ai/api/v1",
            api_key=ENV["LLM_API_KEY"],
        )
        for t, v in zip(batch, vecs, strict=True):
            _vec_cache[t] = v / np.linalg.norm(v)
    return np.stack([_vec_cache[t] for t in texts])


async def rerank(query, documents, top_n=None, **_):
    global _cross
    if RERANKER == "3-large":
        q, docs = await embed_large([query]), await embed_large(documents)
        scores = docs @ q[0]
        order = sorted(range(len(documents)), key=lambda i: -float(scores[i]))[: top_n or len(documents)]
        return [{"index": i, "relevance_score": float(scores[i])} for i in order]
    if _cross is None:
        from sentence_transformers import CrossEncoder

        _cross = CrossEncoder(str(HERE.parent / "models" / "rerankers" / RERANKERS[RERANKER]), device="cpu")
    scores = _cross.predict([(query, d) for d in documents], batch_size=16)
    order = sorted(range(len(documents)), key=lambda i: -float(scores[i]))[: top_n or len(documents)]
    return [{"index": i, "relevance_score": float(scores[i])} for i in order]


async def llm(prompt, system_prompt=None, history_messages=[], **kwargs):  # noqa: B006
    kwargs.pop("temperature", None)  # gpt-5-mini accepts only the default
    return await openai_complete_if_cache(
        ENV.get("AZURE_MODEL", "gpt-5-mini"),
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        base_url=BASE,
        api_key=KEY,
        **kwargs,
    )


async def embed(texts):
    return await openai_embed.func(
        texts, model=ENV.get("AZURE_EMBEDDING_MODEL", "text-embedding-3-small"), base_url=BASE, api_key=KEY
    )


async def make():
    # Our own LightRAG instance: RAG-Anything otherwise refuses to start without MinerU,
    # which only matters for parsing files -- we insert already-parsed text.
    from lightrag import LightRAG
    from lightrag.kg.shared_storage import initialize_pipeline_status

    embedding = EmbeddingFunc(embedding_dim=1536, max_token_size=8192, func=embed)
    light = LightRAG(
        working_dir=str(HERE / "rag_storage"),
        llm_model_func=llm,
        embedding_func=embedding,
        llm_model_max_async=24,
        embedding_func_max_async=8,
        max_parallel_insert=16,
        rerank_model_func=rerank if RERANKER else None,
    )
    await light.initialize_storages()
    await initialize_pipeline_status()
    return RAGAnything(
        lightrag=light,
        llm_model_func=llm,
        embedding_func=embedding,
        config=RAGAnythingConfig(working_dir=str(HERE / "rag_storage")),
    )


async def index(limit):
    rag = await make()
    chunks = DATA["chunks"][:limit] if limit else DATA["chunks"]
    start = time.time()
    await rag.lightrag.ainsert(
        [c["text"] for c in chunks], ids=[c["id"] for c in chunks], file_paths=[c["id"] for c in chunks]
    )
    print(f"indexed {len(chunks)} chunks in {time.time() - start:.0f}s")


async def query():
    rag = await make()
    results, timings = {}, {}
    for mode in MODES:
        ranks, start = [], time.time()
        for q in DATA["queries"]:
            data = await rag.lightrag.aquery_data(
                q["query"], param=QueryParam(mode=mode, chunk_top_k=20, enable_rerank=bool(RERANKER))
            )
            got = [c.get("file_path") for c in data.get("data", {}).get("chunks", [])]
            ranks.append(next((i for i, c in enumerate(got, 1) if c in set(q["correct"])), None))
        results[mode], timings[mode] = ranks, (time.time() - start) / len(DATA["queries"])
    (HERE / f"results-{RERANKER or 'none'}.json").write_text(json.dumps({"ranks": results, "seconds": timings}, indent=1))
    n = len(DATA["queries"])
    print(f"{'mode':8} {'first':>6} {'top 3':>6} {'top 5':>6} {'MRR@10':>7} {'s/query':>8}")
    for mode, ranks in results.items():
        f = lambda k: sum(r is not None and r <= k for r in ranks)  # noqa: E731
        mrr = sum(1 / r for r in ranks if r and r <= 10) / n
        print(f"{mode:8} {f(1):>3}/{n} {f(3):>3}/{n} {f(5):>3}/{n} {mrr:7.2f} {timings[mode]:8.2f}")
    print("\nper subtopic:", " ".join(MODES))
    for i, q in enumerate(DATA["queries"]):
        print(f"{q['name'][:34]:34}", " ".join(f"{str(results[m][i] or '-'):>6}" for m in MODES))


if __name__ == "__main__":
    cmd = sys.argv[1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    asyncio.run(index(limit) if cmd == "index" else query())
