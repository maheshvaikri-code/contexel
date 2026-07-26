"""Context contracts for the reference agent.

Each contract is a named, versioned contexel pipeline that shapes one tool's
output at the tool -> context boundary. Because the stages are deterministic, a
contract produces the same shaped result on every run — the agent sees the same
lens on the repository whether it is step 1 or step 100. That stability is the
"context contract": the shape of what enters context is pinned, not improvised.
"""
from contexel import (
    dedupe,
    pipeline,
    rank,
    select,
    stage,
    trim_to_budget,
    truncate_field,
)

# search_code: keep locators + a short snippet, drop scoring/VCS/noise, bound it.
SEARCH_CONTRACT = pipeline([
    stage(select, fields=["path", "line", "symbol", "snippet", "score"]),
    stage(dedupe, key=["path", "line"]),
    stage(truncate_field, field="snippet", max_tokens=40),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=1200),
])

# read_files: keep path + content, clip very large files to a per-file budget,
# then cap the whole batch.
FILE_CONTRACT = pipeline([
    stage(select, fields=["path", "content"]),
    stage(truncate_field, field="content", max_tokens=600),
    stage(trim_to_budget, max_tokens=2000),
])

# grep: locators + a short preview only.
GREP_CONTRACT = pipeline([
    stage(select, fields=["path", "line", "preview"]),
    stage(dedupe, key=["path", "line"]),
    stage(truncate_field, field="preview", max_tokens=24),
    stage(trim_to_budget, max_tokens=800),
])

# list_dir: just names + kind.
LISTING_CONTRACT = pipeline([
    stage(select, fields=["name", "kind"]),
    stage(trim_to_budget, max_tokens=400),
])
