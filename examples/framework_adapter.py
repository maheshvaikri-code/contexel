"""Pattern 4 — using contexel inside a RAG framework (LangChain / LlamaIndex).

Frameworks pass their own objects (LangChain `Document`, LlamaIndex
`NodeWithScore`). Convert to/from contexel's plain `list[dict]`, shape in the
middle, convert back. Shown here with a tiny local `Document` so it runs
anywhere; swap in `langchain_core.documents.Document` and it is a drop-in
document transformer / node postprocessor.

    python framework_adapter.py
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from contexel import dedupe, rank, truncate_field, trim_to_budget, pipeline, stage


@dataclass
class Document:                      # stand-in for langchain_core.documents.Document
    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def to_records(docs: List[Document]) -> List[dict]:
    return [{"text": d.page_content, **d.metadata} for d in docs]


def to_documents(records: List[dict]) -> List[Document]:
    return [
        Document(page_content=r.get("text", ""),
                 metadata={k: v for k, v in r.items() if k != "text"})
        for r in records
    ]


shape = pipeline([
    stage(dedupe, key="source"),
    stage(truncate_field, field="text", max_tokens=60),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=1000),
])


def postprocess(docs: List[Document]) -> List[Document]:
    """Drop-in document transformer / node postprocessor."""
    return to_documents(shape(to_records(docs)))


if __name__ == "__main__":
    docs = [
        Document("passage " + str(i) + " " + "blah " * 40,
                 {"source": f"doc{i % 5}", "score": (i * 3) % 7})
        for i in range(15)
    ]
    out = postprocess(docs)
    print(f"{len(docs)} docs -> {len(out)} shaped docs")
