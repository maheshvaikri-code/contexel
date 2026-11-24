<p align="center">
  <img src="logo/contexel_logo.png" width="340" alt="contexel logo">
</p>

<p align="center">
  <a href="https://pypi.org/project/contexel/"><img src="https://img.shields.io/pypi/v/contexel?label=pypi" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/contexel"><img src="https://img.shields.io/npm/v/contexel?label=npm" alt="npm"></a>
  <a href="https://www.nuget.org/packages/Contexel"><img src="https://img.shields.io/nuget/v/Contexel?label=nuget" alt="NuGet"></a>
  <a href="https://github.com/maheshvaikri-code/contexel/actions"><img src="https://github.com/maheshvaikri-code/contexel/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/dependencies-0-brightgreen.svg" alt="Zero dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license"></a>
</p>

**The context element.** Deterministic, dependency-free context shaping for
code-writing agents — the same transform, every run.

**Docs site:** [maheshvaikri-code.github.io/contexel](https://maheshvaikri-code.github.io/contexel/)
— architecture with a live budget demo, guides, the stage reference, and the
full benchmark story. Served from this repo's [site/](site/) directory (also
browsable locally: open `site/index.html`).

An agent's tools return big lists of records: search hits, file reads, API
responses. Before they reach the model's context window they must be cut
down — and today that cutting is usually code the model improvises fresh
each run, which drifts: different field choices, different truncation,
different survivors, every time. contexel replaces the improvisation with
vetted, versioned stages at the **tool → context boundary**. Same input,
byte-identical context, on every run.

## What it does, and exactly how

A *record* is a plain `dict`; a collection is `list[dict]` — the shape
tools already return. Every stage is `(records, **params) -> records`,
never mutates its input, and composes with the others:

| Stage | What it does | How, exactly |
|---|---|---|
| `select(records, fields)` | keep only the fields you need | per-record projection onto the keep-list, order preserved |
| `dedupe(records, key=...)` | drop duplicate records | type-qualified fingerprint of the key fields (`1`, `1.0`, `True`, `"1"` stay distinct); first occurrence wins, order preserved |
| `rescore(records, query=...)` | score relevance from evidence, instead of trusting the tool's score | BM25-style, computed inside the batch: per-term IDF `ln((N-df+0.5)/(df+0.5)+1)` × saturating term frequency `tf/(tf+1.5)`, exact word-boundary matching by default (`value` ≠ `values`, snake_case splits; `match="stem"` opts in to a small frozen English stemmer, `normalize="nfc"` to Unicode NFC), plus a bonus when consecutive query terms appear in order within 80 chars |
| `rank(records, by=...)` | order by importance | stable sort on a field or key function; records missing the field go last |
| `truncate_field(records, field, max_tokens=...)` | clip one long text field | longest prefix that fits the token cap — closed-form for the built-in estimator, binary search for custom tokenizers — then `…` |
| `trim_to_budget(records, max_tokens=...)` | keep the top records that fit a budget | greedy prefix: each record costs the token count of its serialized text (+2 list framing); stops before the budget is crossed |
| `allowlist(records, field, allowed)` | provenance gate — refuse unapproved sources | keeps records whose `field` value is in the allowed set; missing or unhashable values are dropped (fail closed); apply *before* any relevance logic |
| `quarantine(records, fields=...)` | tripwire for literal injection markers | case-insensitive pattern screen ("ignore previous instructions", role resets, system tags); `drop` or `flag`, with an opt-in `normalize="nfc"` that also scans the NFC form (it only widens detection) — not a security boundary: paraphrase passes, provenance gating is the stronger control |
| `merge(*sources, schema=...)` | unify differently-shaped tool outputs | maps candidate field names onto one schema, first match wins; optional cross-source dedupe |
| `as_records(x, field="text")` | turn a string, a mapping or a list into records | entry point (outside `pipeline`): a string becomes `[{field: x}]`, a mapping `[x]`, a list keeps its mappings and wraps every other item; `None` and bytes raise `input.not_list` |
| `split(records, field="text", by="lines")` | cut text into chunk records | by lines (after each `\n`), paragraphs (after a run of two or more newlines) or `size` code points; every chunk keeps its separator and an `{index, start, end}` offset, so joining the chunks rebuilds the text exactly |
| `join(records, field="text", sep="")` | turn records back into one string | exit point (outside `pipeline`): strings as they are, anything else rendered the way the budget priced it; records without the field are skipped |

Compose them with `pipeline([...])` — plain function composition, any
`records -> records` callable is a valid stage — or attach a pipeline to a
tool with `@shaped` so the model never sees raw output (async tools are
awaited, then shaped). `trace()` records what every stage removed;
`trace(id_field=...)` additionally records *which* records each stage
dropped, and `t.audit()` emits a JSON-able governance record keyed by the
pipeline's policy fingerprint — a shaping decision is inspectable and
attributable instead of silent. The fingerprint covers what a stage is bound to
(lists, dicts, sets, a nested pipeline used directly as a stage, a tiktoken
encoding), and `stage()`
keeps a private copy of the plain lists, dicts and sets bound to it, so
changing yours afterwards changes neither the behavior nor the fingerprint. A
record that never had the id field is untracked; if a stage strips the id from
the records it keeps (a `select` without it), the trace explains away only as
many missing ids as the stage produced extra id-less records and reports the
rest as dropped, so keep the id field in every `select` for exact attribution.
`split` keeps every id (each chunk carries its parent's fields), so it is attributed
exactly per distinct id value: an empty-text record that vanishes is reported, a
chunk dropped later is reported under its parent's id. Two limits: ids are counted
by value, so with duplicate ids a record that vanished can be hidden by a sibling's
chunks of the same id; and an `id_field` that is the split `field` itself is
rewritten by the split, so a parent cut into several chunks is reported dropped
(the safe side).

All of it is stdlib-only Python. No embeddings, no model calls, no
dependencies — which is what makes the determinism claim checkable: the
benchmark suite hashes the output of the same contract across fresh
interpreters with different `PYTHONHASHSEED` values and gets the same
SHA-256 every time ([benchmarks/RESULTS.md](benchmarks/RESULTS.md)).

## What the benchmark shows — and how to read it

Measured on real, public data: the full CodeSearchNet python/test split
(22,176 functions), reconstructed into 28,047 search-tool records with
genuine duplicates, plus 100 ground-truth episodes where the record the
agent *needed* is known in advance. Full method and tables in
[benchmarks/COMPARISON.md](benchmarks/COMPARISON.md); reproduce with
`python -m benchmarks.competitors` after `pip install -e ".[benchmarks]"`
(the first run downloads the CodeSearchNet split, ~30 MB, and refuses it
unless its SHA-256 equals the digest committed in
`benchmarks/dataset.sha256`).

Every number in this section is generated, or checked against the results: the
tables are rendered from `benchmarks/COMPARISON.json`, and
`python tools/check_benchmark_numbers.py` (run in CI) fails when this file, the
PyPI README or the site disagree with it.

<!-- benchmark:glance:start -->
| Implementation | Native ops | ms @28k | ms/episode | Recall % (strong / weak) | Compliance % | Fill × | Useful % | Import ms | Deps |
|---|---|---|---|---|---|---|---|---|---|
| **contexel** | **6/6** | 74 | 39.6 | **100 / 100** | **100** | 0.95 | **100** | 20 | **0** |
| hand-written | 0/6 | 28 | 3.0 | 93 / 32 | **100** | 0.95 | **100** | — | — |
| hand-written (term overlap) | 0/6 | — | 29.0 | 97 / 97 | **100** | 0.94 | **100** | — | — |
| toolz | 2/6 | 44 | 14.0 | **100 / 100** | 0 | 91.62 | **100** | 13 | **0** |
| langchain-core | 1/6 | 231 | 15.5 | 30 / 30 | **100** | 0.52 | 89.7 | 91 | 25 |
| llama-index-core | 0/6 | 509 | 42.3 | **100 / 100** | 0 | 129.21 | 74.2 | 1,227 | 60 |
<!-- benchmark:glance:end -->

How to read each column, plainly:

- **Native ops** — how many of the task's six operations (select, dedupe,
  rescore, truncate, rank, trim) the library expresses itself, *computed* from
  the code that defines each implementation (`benchmarks/opcount.py`), not
  typed. The two speed columns are different experiments: in `ms @28k`,
  everything a library lacks was filled with the *same* hand-written glue,
  so timing differences are the library's; the Recall / Compliance / Useful
  columns are the opposite — each library acts *only* through its own
  operations, so those numbers show what each one ships. `ms @28k` is the
  query-free bulk task, and "—" marks a row with no timed task.
- **Recall %** (strong / weak retrieval signal) — did the record the agent
  actually needed survive into a 1,500-token context? The episodes guarantee
  that record is present in the raw hits, so recall here isolates *shaping*
  loss, not retrieval loss. contexel's recall is the same under both signals,
  because `rescore` derives relevance from the records' own text; the
  hand-written row trusts the tool's score, so its recall falls when that
  score is poor. The *hand-written (term overlap)* row adds the scorer such
  code would improvise: it is the fairest comparison for `rescore`, another
  rescorer rather than none.
- **Compliance %** — did the final context actually fit the budget? A row with
  full recall and zero compliance (toolz, llama-index) got there by emitting
  many times the budget (the Fill column): a context no window accepts.
- **Useful %** — share of final-context tokens spent on needed fields of
  unique records. langchain-core honors the budget but spends part of it on
  duplicates and field bloat it cannot remove; llama-index spends more.
- **ms/episode is the work, not overhead.** Per episode contexel projects,
  dedupes, scans each record's own text to compute relevance, clips to a
  token-accurate cap, ranks, and enforces the budget. It and the hand-written
  term-overlap scorer are the two slowest budget-compliant rows, in an order
  that can change from run to run: the scorer does less record work (whole-word
  overlap instead of IDF, saturating term frequency and proximity), cuts by
  characters instead of tokens, and trims with a heuristic. Every other
  compliant row is faster because it does less still: the hand-written glue
  trusts the score, langchain-core skips the record work. The timings are one
  selected run (the best of three runs of the command) on one machine; they
  vary with the machine's load and from run to run, and the other columns do
  not.

The same trade shows in `ms @28k`: contexel's time includes token-accurate
truncation and the pipeline's plumbing; the hand-written glue slices at ~4
chars/token and lands looser under the budget. Both are noise next to a
single model call.

**Inflected queries.** The episodes above query with the target's own words,
so exact-word matching is never tested. A second set of episodes keeps the
hit lists but hands the shaper deterministic inflections of those words
(`parse` becomes `parsing`, `returns` becomes `return`; synthetic, the rule is
in `benchmarks/inflection.py`), so exact-word matching fails by construction
and `match="stem"` is measured (only terms the frozen stemmer maps to one stem
are used, so the stem row shows the stem match carrying through ranking and the
budget, not how many English inflections the stemmer covers):

<!-- benchmark:inflected:start -->
| Shaper | Recall % (original terms) | Recall % (inflected terms) |
|---|---|---|
| contexel | 99 | 35 |
| contexel (match=stem) | 98 | 98 |
| hand-written (term overlap) | 96 | 35 |
| hand-written | 90 | 90 |
<!-- benchmark:inflected:end -->

Exact-word matching (the default) collapses on inflected queries, and so does
the hand-written term-overlap scorer; `match="stem"` recovers them (for the
terms the stemmer maps to one stem, which is what the episodes use). The
hand-written row that trusts the tool's score never reads the query, so
inflection cannot touch it: it is the control. This measures inflection
robustness only — not synonyms, not paraphrase, not meaning.

**Limits, measured and stated:** recall@budget has a ceiling no shaper
escapes — when a query legitimately describes more records than the budget
holds, some valid record is cut, semantic or not. And `rescore` is lexical:
exact words by default, so a query saying *parsing* scores zero against a
document saying *parse*. `match="stem"` opts in to a small, frozen English
stemmer that matches those inflections (the table above shows what it
recovers); synonyms and paraphrase are invisible either way. When you need
that, put a semantic reranker in front — contexel's own suite measures what
the lexical lane cannot reach instead of hiding it
([RESULTS.md](benchmarks/RESULTS.md) also quantifies the default
tokenizer's error: −29% on JSON-heavy records — hard token limits require
an exact tokenizer: `contexel[accurate]` + `tokens.use_tiktoken()` where
tiktoken covers the model, or your provider's own counter via
`set_tokenizer`; the estimator is for soft budgeting only).

**And shaping is not an injection defense.** `rescore` ranks textual
relevance; a hostile record that matches the query well ranks well —
including one that says "ignore all previous instructions". contexel ships
two deterministic boundary controls: `allowlist` (a provenance gate —
refuse sources you didn't approve, the strong control) and `quarantine`
(a pattern tripwire for the loud, literal cases — paraphrase passes it).
Both are traced and audited; neither is a semantic guardrail. Content
authentication still belongs *upstream* of the contract, and every shaped
record remains untrusted data, never instructions.

## Where it is used

contexel sits wherever tool output becomes model context:

1. **Inside agent-written code** (programmatic tool calling / code
   execution): the sandbox imports the stages, so the model composes vetted
   transforms instead of improvising them —
   [`examples/programmatic_tool_calling.py`](examples/programmatic_tool_calling.py)
2. **At the tool boundary**: decorate the tool, the model never sees raw
   output — [`examples/tool_boundary_wrapper.py`](examples/tool_boundary_wrapper.py)
3. **Inside an MCP server**: shape responses before they leave the server —
   [`examples/mcp_server.py`](examples/mcp_server.py)
4. **Under a framework**: a `records ⇄ Document` adapter for LangChain /
   LlamaIndex — [`examples/framework_adapter.py`](examples/framework_adapter.py)
5. **Ahead of a token-efficient encoding**: shape-then-encode with
   [ISON](https://ison.dev) — [`examples/ison_boundary.py`](examples/ison_boundary.py)

And a complete, runnable code-execution agent in
[`reference_agent/`](reference_agent/) (`python -m reference_agent`, no API
key needed) whose tests prove the headline guarantee: two runs build
byte-identical context even though the raw tool output carries fresh
request ids every call.

## How to use it

```bash
pip install contexel              # pure Python, zero dependencies
pip install "contexel[accurate]"  # + tiktoken, for exact token counts
```

TypeScript/JavaScript and C#/.NET agents get the same tool, same behavior
([parity details](#language-parity)):

```bash
npm install contexel              # zero runtime dependencies, Node >= 18, ESM
dotnet add package Contexel       # zero runtime dependencies, net8.0
```

From source — also how you get the benchmark suites:

```bash
git clone https://github.com/maheshvaikri-code/contexel && cd contexel
pip install -e ".[benchmarks]"    # everything the benchmark suites use
```

Inline, with the shaping visible and traced:

```python
from contexel import select, dedupe, rescore, truncate_field, rank, trim_to_budget, trace

raw = search_tool(query=user_query)              # a batch of verbose results

with trace() as t:
    r = select(raw, ["title", "url", "snippet", "published"])
    r = dedupe(r, key="url")
    r = rescore(r, query=user_query, fields=("title", "snippet"))
    r = truncate_field(r, "snippet", max_tokens=120)
    r = rank(r, by="score", desc=True)
    r = trim_to_budget(r, max_tokens=1500)

print(t.report())    # per-stage: records in -> out, tokens before -> after

context = r          # only this distilled result enters the model's context
```

Or as a named, versioned policy applied at the tool boundary — a *context
contract* the model can't vary:

```python
from contexel import shaped, stage, select, dedupe, trim_to_budget

@shaped([
    stage(select, fields=["path", "line", "snippet"]),
    stage(dedupe, key=["path", "line"]),
    stage(trim_to_budget, max_tokens=2000),
])
def search_code(query: str) -> list[dict]:
    return repo.search(query)     # raw and heavy — shaped identically, every call
```

Token accounting is pluggable on two axes. The *tokenizer*: the default is
a dependency-free ~4-chars/token estimate; `contexel.tokens.use_tiktoken()`
switches to exact counts for models tiktoken covers (other providers: plug
their own counter via `set_tokenizer(fn)`). The *serializer*: budgets are
encoding-relative — a record's cost is the token count of its serialized
text, canonical JSON by default. If your boundary emits something else (an
ISON table, say), `contexel.tokens.set_serializer(fn)` keeps budgets priced
in the encoding that actually enters context. For concurrent tenants, both
axes can be overridden per task with `tokens.scoped(...)` — a context-local
overlay that never touches other tasks (bare threads start fresh and fall
back to the process default).

### Text, logs and web pages

Stages take a list of mappings, and a log, a web page or a plain string is
none of that. Three small stages convert at the edges: `as_records` turns a
string (or one mapping, or a list) into records, `split` cuts the text of each
record into chunk records, and `join` turns records back into one string.
Everything in between is an ordinary stage. Call `as_records` and `join`
outside `pipeline`, as you call `merge`: a pipeline hands every stage a list,
and a strict pipeline rejects `join`'s string, naming the stage.

```python
from contexel import (as_records, dedupe, join, pipeline, rank, rescore,
                      split, stage, trim_to_budget)

log = "INFO started\nWARN retry limit reached\nINFO ok\nINFO ok\nERROR timeout after retry\n"

pipe = pipeline([
    stage(split, by="lines"),                              # one record per line
    stage(dedupe, key="text"),                             # the repeated "INFO ok" goes
    stage(rescore, query="retry timeout", fields=["text"]),
    stage(rank, by="score"),
    stage(trim_to_budget, max_tokens=60),
])
best = pipe(as_records(log))
print(join(best), end="")
print([c["chunk"]["start"] for c in best])                 # offsets into the log
```

```text
ERROR timeout after retry
WARN retry limit reached
[54, 13]
```

The cuts are the same in Python, TypeScript and C#:

| `by` | a chunk ends |
|---|---|
| `"lines"` (default) | after each `\n`: `\r\n` is one boundary and a lone `\r` is none (Python's wider `splitlines` set is not used) |
| `"paragraphs"` | after each run of two or more newlines, `(?:\r?\n){2,}` |
| `"size"` | every `size` code points (`size` is a required positive integer, and only valid with this mode) |

- Every chunk keeps its trailing separator, so `join(split(as_records(text)))`
  returns `text` exactly. Each chunk is a copy of its parent record with the
  text replaced and `{"index", "start", "end"}` stored under `into` (default
  `"chunk"`): `text[start:end]` is the chunk, and offsets and sizes count code
  points in every language.
- A record whose text field is not a string passes through untouched; an empty
  text produces no chunks, so that record disappears; a record whose text is a
  string and that already has the `into` key raises `input.field_conflict`.
- These stages check their input in every mode, not only in strict mode: a
  non-list raises `input.not_list` and a non-mapping item `input.not_mapping`.
- `join` renders a value that is not a string the way the token budget priced it
  (`tokens.serialize`) and skips records that lack the field.
- `rank` reorders the chunks by score. To restore reading order before `join`,
  rank again on the offset with a named key function (a dotted path such as
  `"chunk.start"` is not supported):

```python
from contexel import as_records, join, rank, split

chunks = split(as_records("one\ntwo\nthree\n"), by="lines")
by_length = rank(chunks, by=lambda r: len(r["text"]))
in_order = rank(by_length, by=lambda r: r["chunk"]["start"], desc=False)
print(repr(join(by_length)))
print(repr(join(in_order)))
```

```text
'three\none\ntwo\n'
'one\ntwo\nthree\n'
```

Overlapping windows and token-sized chunks are not offered: they either break
losslessness or need a tokenizer every language shares.

**Limits.** `split` has no cap: it makes one record per boundary, and each chunk
is a copy of its parent record. Measured on a development machine (orders of
magnitude, not guarantees): at one chunk per input character, a 1,000,000-character
text retains roughly 440 MB in Python, 140 MB in TypeScript and 540 MB in C#, and
time is linear (about 0.4 to 2 seconds per million chunks). Every chunk carries the
parent's other fields, so anything that prices or serializes each chunk in full (a
`trace`, `trim_to_budget`) costs about the number of chunks times the size of those
fields: with a 50,000-character side field and 4,000 chunks a traced `split` took
about 0.6 to 2 seconds, and the cost grows with both. When the text is untrusted,
cap its size before `split`, and keep only the fields you need (`select`) before
it. The memory of the paragraph cut does not grow with the length of a newline
run. A cap option may be considered later.

### Matching: stems and Unicode forms

`rescore` counts exact words by default, the way BM25 and Lucene do: `parse` does
not match `parses` or `parsing`, and `café` typed as one character does not match
`café` typed as `e` plus a combining accent. Two opt-in switches widen what a match
means. Neither changes any default output.

`match="stem"` reduces every word of the query and of the text to its stem first,
so `parse`, `parses`, `parsed` and `parsing` count as one term:

```python
from contexel import rescore

notes = [
    {"id": 1, "snippet": "Parses every line, then keeps parsing until the end"},
    {"id": 2, "snippet": "Parsed rows are cached"},
    {"id": 3, "snippet": "Nothing about this topic"},
]
exact = rescore(notes, query="parse", fields=["snippet"])
stemmed = rescore(notes, query="parse", fields=["snippet"], match="stem")
print([r["score"] for r in exact])
print([r["score"] for r in stemmed])
```

```text
[0, 0, 0]
[0.268574, 0.188001, 0]
```

The stemmer is a short, ordered list of suffix rules (plural `s`, `ies`, `ied`,
`ing`, `ed`, a final `e`) that Python, TypeScript and C# repeat exactly; the whole
table, with worked examples, is [docs/stemmer-rules.md](docs/stemmer-rules.md).
It is English only and not a lemmatizer: `configure` and `config` stay apart and
`speed` becomes `spe`. It is **frozen**: an improvement will ship under a new
`match` name, never as an edit, so a policy that says `match="stem"` keeps meaning
the same thing. Scoring, IDF, the proximity bonus and the rounding are those of
`match="word"`, and a position is the start of the word, counted in code points.

`normalize="nfc"` applies Unicode NFC to the query and the text before they are
lower-cased in `rescore`, and makes `quarantine` scan the text in its NFC form as well:

```python
from contexel import quarantine, rescore

precomposed = "caf\u00e9"       # one code point
decomposed = "cafe\u0301"       # "cafe" plus a combining acute accent: it looks the same
records = [{"snippet": "the " + precomposed + " opens"},
           {"snippet": "the " + decomposed + " opens"},
           {"snippet": "tea"}]
print([r["score"] for r in rescore(records, query=precomposed)])
print([r["score"] for r in rescore(records, query=precomposed, normalize="nfc")])
for normalize in (None, "nfc"):
    flagged = quarantine(records, fields=["snippet"], patterns=[precomposed + " opens"],
                         action="flag", normalize=normalize)
    print([r["quarantined"] for r in flagged])
```

```text
[0.392332, 0, 0]
[0.188001, 0.188001, 0]
[True, False, False]
[True, True, False]
```

- `quarantine` with `normalize="nfc"` scans the text as it is and also in its NFC form, and a record is hit when either
  matches: the option can only add detections, never hide one the default catches (a
  combining mark after the last letter of a marker cannot hide it). It never
  normalizes the patterns: a pattern written in decomposed form matches a
  decomposed spelling of the text with or without `normalize`, and never matches a
  precomposed one. The built-in patterns themselves are not changed.
- The default is `None`. Any other value than `None` and `"nfc"` (`"NFC"`, `"nfd"`,
  a typo) raises `config.invalid_value` instead of quietly doing nothing.
- **Margin.** Each runtime ships its own Unicode database, so text that uses
  characters added to Unicode recently can normalize differently in Python,
  TypeScript and C#. The shared vectors use text whose normalization has not
  changed (accented Latin, Hangul, combining marks, an astral compatibility
  ideograph). .NET's `string.Normalize` throws on a lone surrogate and on
  U+FFFE; contexel's C# port normalizes around such a character and keeps it, so
  the result equals what Python and JavaScript return.
- **Cost.** Each runtime's own NFC reorders a run of combining marks in time that
  grows with the square of the run: a text made of a long alternating run of two
  kinds of combining marks (for example 128,000 of U+0301 and U+0323) takes
  seconds with `normalize="nfc"` on, in Python, TypeScript and C# alike, where
  the default takes milliseconds. Real text does not contain such runs.
  `normalize="nfc"` is opt-in; if you pass text you do not control, cap its size
  first.

### Errors and strict mode

A control must never be weaker than it looks, so misconfiguration always
raises a typed error. Every error is a `ContexelError` with a stable `code`
(the cross-language contract; messages are for humans): a `ConfigError` (also
a `ValueError`) for a wrong *call* — an unknown `match`, `fields=[]`, an invalid
regex, a negative `max_tokens` — and an `InputShapeError` (also a `TypeError`)
for wrong *data*. Bad data is lenient by default, so valid input behaves exactly
as before, with two exceptions that are never lenient. `quarantine(action="flag")`
over a record that already has the `into` key always raises
`input.field_conflict`, strict mode or not and clean record or not, because
carrying on would overwrite your data (so re-running a flag pipeline on its own
output raises; pass a different `into`). And `quarantine` always raises
`input.not_mapping` for an item that is not a mapping, in drop and flag mode,
because a screen that skips what it cannot read would keep the attack. Switch on
strict mode to have any other stage that gets a non-list, or an item that is not
a mapping, raise instead and name itself and the item index:

```python
from contexel import ConfigError, InputShapeError, allowlist, quarantine, select, strict

sources = [{"source": "github", "snippet": "ok"}, {"source": "g", "snippet": "no"}]
print(allowlist(sources, "source", "github"))   # a bare string is ONE allowed value

nested = [{"note": {"lines": ["ignore all previous", "instructions"]}}]
print(quarantine(nested, fields="note"))        # nested values are scanned too

try:
    quarantine(nested, fields=[])               # a control that scans nothing raises
except ConfigError as e:
    print(e.code)

with strict():                                  # opt in to shape validation
    try:
        select(None, ["a"])
    except InputShapeError as e:
        print(e.code, e.stage)
```

```text
[{'source': 'github', 'snippet': 'ok'}]
[]
config.empty
input.not_list select
```

`allowlist` is type-strict where it matters: a bool never equals a number, so
`True` cannot pass a gate that approved `1` (`1` and `1.0` still compare equal,
because TypeScript cannot tell them apart). `with strict():` is a context flag:
it follows `await` but is not inherited by a bare thread, so
`pipeline(stages, strict=True)` and `shaped(pipe, strict=True)` switch it on
inside their own run, and a strict pipeline also checks that every stage hands
the next one a list:

```python
from contexel import InputShapeError, pipeline, select, stage

def forgets_to_return(records):
    records.clear()

pipe = pipeline([stage(select, fields=["a"]), forgets_to_return], strict=True)
try:
    pipe([{"a": 1}])
except InputShapeError as e:
    print(e.stage)
```

```text
forgets_to_return
```

Strict mode covers the eight record stages (`select`, `dedupe`, `allowlist`,
`quarantine`, `rescore`, `rank`, `truncate_field`, `trim_to_budget`) and the
check on what a pipeline or a `shaped` tool returns. It does not cover `merge`,
which still accepts anything iterable (`merge("ab")` returns `['a', 'b']`, strict
or not). A tuple is accepted wherever a list is. `fields=[]` raises
`config.empty` for `quarantine` and `rescore` only; `select(records, [])` still
returns `[{}, ...]`.

The payload stages (`as_records`, `split`, `join`) are new, so they check their input
in every mode instead of only in strict mode (see [Text, logs and web pages](#text-logs-and-web-pages)).

A `strict()` object keeps its own token stack, so one object can be entered
again, nested or one use after another, and each exit restores the previous
state. Sharing ONE object between asyncio tasks or threads whose uses overlap
can fail instead (`ValueError: ... was created in a different Context`): call
`strict()` for each use.

Differences between the languages (the codes are the contract, the rest can
differ):

- **Regex dialect.** `quarantine` compiles the built-in markers once and each
  custom pattern on its own, with each language's own regex engine, and drops
  or flags a record when any of them matches. Whether a pattern is invalid
  (`config.invalid_pattern`; the message names the pattern) is per port:
  `(?P<a>x)` is valid in Python only and `(?<a>x)` in TypeScript and C# only;
  TypeScript rejects the global inline-flag form `(?i)x` (matching is already
  case-insensitive there), and accepts the scoped modifiers `(?i:...)` and
  `(?-i:...)` only on newer engines (Node 24 accepts them; older Node versions
  were not tested here), so their validity depends on the Node version, while
  Python accepts a leading `(?i)` and `(?i:...)`, C# accepts the flags .NET
  supports, and a flag affects only its own pattern; `\Z` is a literal `Z` in
  TypeScript and an end anchor in Python and C#; a lone `\1` (a back-reference
  with no group of its own) is a legacy octal escape in TypeScript, so it is
  valid there and matches U+0001, but it is `config.invalid_pattern` in Python
  and C#; the Kelvin sign U+212A is folded to `k` by Python and C# but not by
  TypeScript.
- **Each pattern means what it says on its own.** Before this release the
  built-ins and your custom patterns were joined into one regex, so one pattern's
  inline flags and group numbers leaked into the others. A custom pattern can
  therefore no longer weaken or silently disable the built-ins, and a few
  records that were dropped only because of the leak are now kept: on Python 3.9
  `patterns=["(?s)zz", "c.d"]` dropped `"c\nd"` and now keeps it (the `(?s)`
  was applying to `c.d`), and with `replace_patterns=True`,
  `["(?m)^admin:", "^ignore"]` dropped `"hello\nignore"` and now keeps it. This
  is the intended behaviour, but a pattern list that relied on the leak must be
  rewritten (give each pattern its own flags).
- **Integral floats.** `max_tokens=1000.0` is rejected in Python and accepted in
  TypeScript, which has one number type.
- **`null` as a default.** TypeScript raises for `fields: null`, as Python does
  for `fields=None`; C# treats `fields: null` as "use the default fields" for
  `quarantine` and `rescore`, because it cannot tell an omitted optional
  argument from an explicit `null` without changing its public API.
- **Messages.** They differ between ports and are not part of the contract
  (TypeScript's say `NoneType` and `None`, for instance).

Public helpers the code exposes beyond `__all__`: `contexel.validate.is_strict()`
(is strict mode active here) and `contexel.errors.CODES` (the stable error
codes).

Known limitations (documented, not fixed in this release). `quarantine` is a
tripwire for literal markers, not a security boundary, and the three ports do
not catch exactly the same obfuscations:

- The built-in markers differ per engine: U+0085 is caught by Python and C# and
  kept by TypeScript; U+001C to U+001F are caught by Python only; U+FEFF by
  TypeScript only; dotless i and dotted I (U+0131, U+0130) and long s (U+017F,
  in "system prompt") by Python only.
- None of the ports catches zero-width characters (U+200B, U+2060), RLM and RLO
  marks, a soft hyphen (U+00AD), combining marks, homoglyphs (Cyrillic U+0430 for
  `a`), fullwidth forms, `&nbsp;`, a marker split across two sibling dict values
  (the key sits between them) or `< /system >`.
- A misspelled name in `fields` (`"snipet"`) scans nothing and keeps everything,
  strict mode or not, in all three languages; so does `fields=""`. Check field
  names against your records.
- A custom pattern runs on attacker-controlled text and no port sets a match
  timeout: `(a+)+$` is exponential on crafted input (the built-ins are linear).
  Do not accept patterns from untrusted sources. A pattern that matches the empty
  string (`a*`) drops every record.
- A shared in-process container is expanded once, so a marker that needs the same
  list twice is not found (JSON-decoded input never shares structure). A `set`,
  `frozenset`, `deque` or dict view is not expanded: it is scanned as its `str()`
  text, so a marker split by a newline inside one is kept. The same holds for a
  `collections.abc.Mapping` that is not a `dict` when it is a field value (not an
  item): a `MappingProxyType` is scanned only through its `str()` and `repr()`, so
  one holding a newline-split marker is kept.
- A leaf that is not a string, number, boolean or `None` (a `Decimal`, `datetime`,
  `Enum` or `UUID`, at the top level of a field as well as nested) is scanned as
  its `str()` text and, when it differs, its `repr()`, so a custom pattern can
  match the `repr()` only (`Decimal('5')` for `Decimal("5")`) and an anchored
  pattern such as `^5$` no longer matches a `Decimal("5")` field, whose scanned
  text is `5 Decimal('5')`. An object whose `__repr__` raises makes `quarantine`
  raise that exception unchanged (it fails closed, but it is not a
  `ContexelError`), and side effects in `__repr__` run. Exact `int`, `float`,
  `bool` and `None` leaves skip the `repr()` call, and dict keys are scanned with
  `str()` only.
- `allowlist`: a `None` entry in `allowed` admits records that lack the field (a
  trap with `os.environ.get(...)`); `float("nan")` in `allowed` matches only the
  same object; and, unlike `quarantine`, a non-mapping item raises a raw
  `AttributeError` rather than `input.not_mapping` (a follow-up is planned).
- `dedupe(records, key=[])` and `key=""` keep only the first record. A very deep
  value under an active `trace()` raises `RecursionError`.
- In C#, `System.Text.Json` `JsonElement` and `JsonNode` values are not read by
  `quarantine` or `allowlist`; see the C# README.

## Alternatives, and what pairs with it

The tool → context shaping *pattern* is industry consensus; what varies is
the mechanism. The nearest neighbours, so you can pick deliberately:

- **LangChain** `trim_messages` token-trims *chat turns*, not tool records;
  `EmbeddingsRedundantFilter` dedupes semantically — it needs an embedding
  model, and results shift with model versions. **Haystack** `DocumentJoiner`
  and **LlamaIndex** node postprocessors cover similar operations, coupled to
  their frameworks' `Document`/node types. **`context-engineering-toolkit`**
  has been cited as the closest standalone library but was not on PyPI as of
  2026-07.
- **Semantic compressors** (LLMLingua, ColBERT, cross-encoder rerankers)
  understand meaning; contexel is deterministic and lexical by design —
  complementary, not superior. The comparison measures exactly where that
  line sits.
- **The pattern itself** (Anthropic's "code execution with MCP", Cloudflare
  Code Mode) ships as a description, with the shaping left to code the model
  improvises each run — the drift contexel exists to remove.

**Serialization formats are the complementary layer, not competitors**:
contexel decides *what survives*; the encoding decides *what the survivors
cost*. It pairs naturally with [ISON](https://ison.dev) — `select` projects
records onto a uniform field set, exactly the rows ISON's table syntax
encodes without repeating keys (measured in benchmark suite 6), and
`tokens.set_serializer()` keeps budgets priced in that encoding (see
[`examples/ison_boundary.py`](examples/ison_boundary.py)).

Measured, not asserted: [`benchmarks/COMPARISON.md`](benchmarks/COMPARISON.md)
runs the same shaping task through the nearest neighbours on real
CodeSearchNet records (`python -m benchmarks.competitors`), and
[`benchmarks/RESULTS.md`](benchmarks/RESULTS.md) covers contexel's own claims
(`python -m benchmarks` — needs the `accurate` extra; the competitor run
needs the `benchmarks` extra).

## Design

- Every stage is `(records, **params) -> records` over plain `list[dict]`,
  never mutates its input, and is deterministic — no randomness, no wall
  clock, no model calls. That is what lets a pipeline be a *versioned
  contract* rather than a convenience.
- Stages are stateless between calls. contexel pins the *shaping*; it cannot
  make nondeterministic retrieval or a changed repo identical, and it is not
  a memory layer.
- The deterministic stages are free and reproducible. Model-augmented stages
  (semantic reranking, summarization, semantic dedupe) would layer on top
  behind an injected client — deliberately out of scope today.

## Language parity

The same tool ships for three ecosystems — Python
([PyPI](https://pypi.org/project/contexel/)), TypeScript/JavaScript
([npm](https://www.npmjs.com/package/contexel), the [ts/](ts/) directory),
and C#/.NET ([NuGet](https://www.nuget.org/packages/Contexel), the
[csharp/](csharp/) directory). The ports are **parity ports, not
re-imaginings**: the Python implementation is canon, and every language
runs its test suite against the same golden vectors
([parity/vectors.json](parity/vectors.json), generated by
[parity/generate_vectors.py](parity/generate_vectors.py)) — every stage,
the composed contract pipeline, the audit record, canonical serialization,
token counts, and a growing block of adversarial edge cases must match or
the build is red, on Linux, Windows, and macOS.

What carries over exactly: all eight record stages, `merge` and the
payload stages `as_records`, `split` and `join`,
pipeline composition with policy fingerprints, `shaped` (async tools are
awaited, then shaped), `trace`/`audit`, code-point token counting
(`"café"` costs the same everywhere), and scoped per-tenant token
accounting (`contextvars` / `AsyncLocalStorage` / `AsyncLocal`). The
deliberate boundaries differ per language and are recorded in the ADRs:
JS collapses `1.0` to `"1"` in serialization
([ADR-001](docs/adr/001-typescript-parity.md)) while .NET preserves the
int/float distinction and matches Python exactly there
([ADR-002](docs/adr/002-csharp-parity.md)); Unicode case-folding and word
classes differ at the margins; pipeline fingerprints are language-local
in v1.

[![SkillDen](https://skillden.cv/card/maheshvaikri-code.svg?theme=certificate)](https://skillden.cv/u/maheshvaikri-code?theme=certificate)

## License

MIT
