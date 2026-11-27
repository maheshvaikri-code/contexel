> Filed 2026-11-27 from an independent re-audit of the rewritten text on branch head 9234c25 (branch `docs/benchmark-claims-phase1`, contexel 0.1.17). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. The audit text is kept as written; what was done about each finding is recorded in `docs/plans/foundation-hardening.md` and in the CHANGELOG.

# contexel benchmark claims: independent re-audit of the rewritten text

Audited: 2026-11-26. Branch `docs/benchmark-claims-phase1`, head 9234c25 (base main 1825844), contexel 0.1.17.
The repository was treated as read-only. Every experiment imported the harness from a separate scratch
directory with `PYTHONDONTWRITEBYTECODE=1`; `git status --porcelain` was empty before and after every run.
Environment: Python 3.12.7, Windows 11 (AMD64); toolz 1.1.0, langchain-core 1.4.9, langchain-community 0.3.27,
llama-index-core 0.14.23 and tiktoken 0.8.0 installed. The CodeSearchNet cache was already present and was only read.

My own findings (sections 1 to 4) were written before I opened the two earlier audit files. The cross-check is in section 5.

## 0. Bottom line

* **The rewrite is a real improvement.** Several things were fixed:
  * the Compliance column and the "full marks" sentence are gone from every published surface;
  * the benchmark now says the author wrote it, and asks the compared libraries' maintainers for corrections;
  * the wiring is labelled "in this wiring";
  * the ISON authorship is disclosed wherever ISON is recommended;
  * "proven" became "tested";
  * the made-up tracing numbers on stages.html are gone;
  * the Anthropic and Cloudflare text is no longer "ships as a description".

  `tools/check_benchmark_numbers.py` passes. Every generated number I recomputed matches.
* **The rewrite introduced two new factual errors** in its new text about other projects:
  1. It recommends llama-index-core's `ChatMemoryBuffer` (six places) as the budget step. The class is deprecated in the very version that was measured.
  2. It describes LLMLingua as having no ranking and no lexical rescoring. LLMLingua's `compress_prompt` ranks contexts, BM25 among its options.
* **Two disclosures stop short of the number that matters:**
  * langchain-core returns an **empty context in 31 of 100 episodes**, which the Useful metric scores as 100 % useful. The text mentions that empty contexts can happen, but not how often.
  * "Most of the contexts that fill the budget run over it" leaves out the size: **94 of 100** contexel contexts exceed 1,500 cl100k tokens, by **8 % on average and up to 20 %**. On the same site, a card titled "Budgets that hold" and a Suite 1 row saying "worst overshoot +0.5 %" sit next to that sentence.
* **"langchain-core never reads the score" is a property of the wiring, not of langchain-core.** A Python `sorted()` before the same `trim_messages` gives 78 % / 6 % instead of 30 % / 30 %.
* **The index page shows langchain-core's 396 ms and llama-index-core's 464 ms for `ms @28k` without saying that the time is mostly object construction the benchmark inserted.** The README and the benchmarks page do say this.

## 1. Statements that are NOT plainly fine

Verdicts: CBFR = CORRECT-BUT-FRAMING-RISK.

| id | file:line | exact text (trimmed) | verdict | evidence | proposed replacement |
|---|---|---|---|---|---|
| R1 | README.md:142, 176, 737; site/benchmarks.html:145, 150, 157; COMPARISON.md:105, 221 (rendered from competitors.py:1059-1062 and 1159-1163) | "a token-limited `ChatMemoryBuffer`"; "Both can be given one (toolz `accumulate`; llama-index-core `ChatMemoryBuffer`, or `PromptHelper` ...)"; "LlamaIndex offers related operations on its node types: ... a `ChatMemoryBuffer` token limit" | NEW-REGRESSION (OUTDATED) | Installed llama-index-core 0.14.23, the measured version, has this class docstring: "Deprecated: Please use `llama_index.core.memory.Memory` instead." `Memory` has a `token_limit` field. `ChatMemoryBuffer` also holds `ChatMessage`s, not nodes; `PromptHelper` works on text chunks. So "on its node types" is wrong for both. PyPI's latest is 0.14.26 (`pip index versions`, 2026-11-26). | "...and a token-limited chat memory (`llama_index.core.memory.Memory(token_limit=...)`, which replaces the deprecated `ChatMemoryBuffer`)". Rephrase the list as "on its node, text and chat-message types". |
| R2 | COMPARISON.md:123 (competitors.py:818-823, NOT_RUN) | LLMLingua row: rescore(lexical) "no", rank "no" | NEW-REGRESSION (INCORRECT) | microsoft/LLMLingua `llmlingua/prompt_compressor.py` (main, fetched 2026-11-26): `get_rank_results` dispatches on `rank_method == "bm25"`, `"longllmlingua"`, `"llmlingua"`, and also gzip, sentbert, openai, bge, bge_reranker, bge_llmembedder, jinza, voyageai and cohere. `compress_prompt` also has `reorder_context` ("original" / "two_stage"). So LLMLingua ranks whole contexts, including by BM25, which is lexical, before it compresses tokens. | rank: "ranks contexts (`rank_method`: LongLLMLingua question-aware, `bm25`, embedding or reranker models) and can reorder them (`reorder_context`)". rescore(lexical): "BM25 context ranking (`rank_method="bm25"`)". dedupe: "no". |
| R3 | README.md:180-183; site/benchmarks.html:166-169; COMPARISON.md:168-171 | "A context that is empty counts as fully useful by the current scoring; langchain-core returns one when its first record alone exceeds the budget." | MISLEADING (by omission of the frequency) | My re-run of the published wiring: **31 of 100** langchain-core contexts are empty. In all 31 the first raw record alone costs 1,580 to about 4,950 estimated tokens (median 4,950). Useful over the 69 non-empty contexts is **85.1 %**, not 89.7 %. Fill 0.52 averages in the 31 near-zero contexts. Recall 30 % is 30 of 69 non-empty contexts. | "...langchain-core returns an empty context in 31 of the 100 episodes (its first raw record alone exceeds the budget); its useful share over the 69 non-empty contexts is 85.1 %." Better: score an empty context as 0 % useful, or exclude it and report the count. Generate the count from the JSON. |
| R4 | README.md:163-164; site/benchmarks.html:162-164; COMPARISON.md:215-217 | "langchain-core never reads the score, so both of its columns reflect the same weak per-term incoming order" | MISLEADING | Nothing in langchain-core stops a user from sorting. It is the outcome wiring (competitors.py:340-345) that passes raw hits straight to `trim_messages`. The same native `trim_messages` step after a plain Python sort by score: **78 % strong / 6 % weak** (fill 0.72 / 0.48). After the shared select, dedupe and rank glue: 81 / 9. The hand-written row may use Python's `sorted`; the library rows may not. That asymmetry is not stated. | "This langchain-core wiring never reads the score (langchain-core has no record-ranking step, and the outcome rows get no Python glue), so both columns reflect the weak per-term incoming order. With a Python sort by score before the same `trim_messages`, recall is 78 % / 6 %." |
| R5 | README.md:115-116, 258-259; README_PYPI.md:114-115; site/benchmarks.html:95-97; COMPARISON.md:35-36 | "Measured with an exact tokenizer, most of the contexts that fill the budget here run over the estimated budget." | CBFR (true, but the size is missing and nothing checks it) | `tiktoken` cl100k_base on the published wiring: **contexel 94/100 over 1,500, mean 1.08x, max 1.20x**. o200k_base: 95/100. Hand-written: 91/100 (mean 1.06x, max 1.18x). Term overlap: 92/100. langchain-core: 21/100. "Most" is true, but a reader cannot tell 1 % over from 20 % over. Nothing generates or checks the sentence. | "Counted with tiktoken cl100k_base, 94 of contexel's 100 contexts exceed 1,500 tokens (mean 1.08x, at most 1.20x the budget)." Generate these from the results and register them with the checker. |
| R6 | site/index.html:67-70 | "**Budgets that hold** ... `trim_to_budget` and `truncate_field` enforce the limits you set" | CBFR (contradicts R5) | Under the default estimator the budget holds only as estimated, and on this benchmark's records real contexts run up to 20 % over. The site's own benchmarks page now says so. Suite 1's row "worst overshoot +0.5 % of the budget, measured with tiktoken" (site/benchmarks.html:56) is from synthetic data. Shown next to R5 with no magnitude, it suggests the estimator is nearly tight. | "Budgets in your tokenizer's units: exact with `use_tiktoken()` or your provider's counter; the default estimate is for soft budgets (up to 20 % over on the comparison's JSON records)." |
| R7 | site/index.html:120-123 | "contexel is the row that keeps the needed record in every episode ..., stays within the budget on average (Fill at most 1.00) and spends no tokens on duplicates or bloat" | CBFR | Fill is in estimated tokens. In cl100k tokens contexel's mean fill is 1.08, so it does *not* stay within the budget on average. "No tokens on duplicates or bloat" is true by construction, because the field list and key are contexel's (stated earlier in the same note). | "...stays within the budget on average as the estimator counts it (Fill at most 1.00; about 1.08 in cl100k tokens)..." |
| R8 | site/index.html:92-97 and the glance table (ms @28k column) | "`ms @28k` is the separate shared-glue canonical task" | MISLEADING (the disclosure is missing on this page) | The README (lines 142-148) and benchmarks.html (lines 121-126) explain that the langchain-core and llama-index-core times are mostly converting records to the library's type. The index page shows 396 and 464 with no such note. My re-run (loaded machine) of the timed llama row: `to nodes` about 400 ms of 455 ms total, and no llama operation runs at all. For langchain: wrap about 258 ms against `trim_messages` 19 ms. | Add: "For langchain-core and llama-index-core most of `ms @28k` is the benchmark converting records to the library's message or node type (no llama-index-core operation runs in that task)." |
| R9 | README.md:166-171; README_PYPI.md:125-129; site/benchmarks.html:202-207; COMPARISON.md:195-199 | "with the bonus switched off contexel's recall on these episodes is not above the term-overlap baseline's (this benchmark does not generate that row)" | UNVERIFIABLE for a reader (true when re-run) | `rescore(..., proximity=False)` in the published contract: **95 / 95** recall, against the term-overlap row's 97 / 97. So the claim holds, and it understates: the result is *below* the baseline. A reader cannot check this from the published results. | "...with the bonus switched off (`proximity=False`) contexel's recall on these episodes is 95 %, below the term-overlap baseline's 97 %." Generate that row. |
| R10 | README.md:91-93 and the glance tables on README, README_PYPI, site/index.html and site/benchmarks.html | Library rows named without versions | OUTDATED (framing) | Measured: toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23. Latest on PyPI on 2026-11-26: toolz **1.2.0**, langchain-core **1.8.5**, llama-index-core **0.14.26**, langchain-community **0.4.2** (installed: 0.3.27), haystack-ai **3.5.0**. Only COMPARISON.md and constraints.txt name the measured versions. | Add to each table caption: "measured with toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23 (2026-11-24); newer releases are not measured." |
| R11 | README.md:750-752 | "Anthropic (programmatic tool calling; code execution with MCP) and Cloudflare (Code Mode in the Agents SDK) ship the execution mechanism." | INCORRECT (minor; partly) | Programmatic Tool Calling ships, in beta (anthropic.com/engineering/advanced-tool-use, 2025-11-24: "These features are available in beta"). Cloudflare Code Mode ships in the Agents SDK (blog.cloudflare.com/code-mode, 2025-09-26; developers.cloudflare.com/agents/tools/codemode, changelog 2026-07-22). But "Code execution with MCP" (anthropic.com/engineering/code-execution-with-mcp, 2025-11-04) describes an approach, with illustrative code and no product release. | "Anthropic (Programmatic Tool Calling, in beta; the 'code execution with MCP' approach it describes) and Cloudflare (Code Mode in the Agents SDK) provide or describe the execution mechanism." |
| R12 | README.md:165; site/benchmarks.html:202; COMPARISON.md:195 | "it is the fairest comparison for `rescore`" | CBFR (unsupported superlative) | The author wrote both the baseline and the episodes. The queries are the target docstring's first words in their original order, and the snippet scored *is* that docstring. The proximity bonus that decides the result fires on exactly that construction. The caveat is stated, but "fairest" still asserts a ranking of fairness. | "it is the closest comparison for `rescore` in this benchmark (another rescorer, not none), with one caveat: ..." |
| R13 | README_PYPI.md:107-110; the glance tables ("hand-written (term overlap) 0/6") | "contexel performs all six operations itself, and in the wirings this benchmark chose no other compared row does (hand-written glue, the hand-written term-overlap baseline, ...)" | CBFR / MISLEADING (low) | The term-overlap row does perform all six operations (all six in glue: COMPARISON.md operations table). "0/6" counts only *library* code, and for hand-written rows it is 0 by definition (`root is None`). Read plainly, the sentence says that row does not perform them. | "contexel performs all six with its own stages; the hand-written rows do them in plain code (0/6 is the count of library steps, zero by definition); in the wirings this benchmark chose, no other library performs more than two." |
| R14 | COMPARISON.md:1; competitors.py:1, 121-122, 431, 439 (Impl notes, committed in COMPARISON.json `task[].note`) | "# contexel vs prior art"; notes "what model-improvised shaping looks like", "node round-trip tax; postprocessors fit no stage"; glue comment "this is what improvised code looks like" | CBFR (residual loaded wording) | The site and README dropped "prior art" and "improvised". The report title and the published JSON keep them. "postprocessors fit no stage" contradicts the new "related operations" text. | Title "contexel and other libraries: comparative benchmark"; notes "shared glue (trusts the tool's score)", "node round-trip only (no llama-index-core operation in the timed task)". |
| R15 | COMPARISON.md:3; RESULTS.md:3 | "Generated 2026-11-24 by `python -m benchmarks.competitors`" | CBFR (low) | The prose was re-rendered from the committed JSON (`check_benchmark_numbers.py --write`) and contains "as of 2026-11-26". The header attributes text to a run that did not produce it. | "Numbers generated 2026-11-24 by `python -m benchmarks.competitors`; report text rendered from COMPARISON.json." |
| R16 | README.md:317 | "`pip install -e ".[benchmarks]"    # everything the benchmark suites use`" | CBFR (inconsistent) | Three other places in the same README say to add `-c benchmarks/constraints.txt` to get the measured versions. | Add `-c benchmarks/constraints.txt` here, or point to the benchmark section. |
| R17 | COMPARISON.md:152-153 | "up to the first three words of at least five characters in its docstring, in their order" | CBFR (NIT) | The length is measured *before* punctuation is stripped (competitors.py:602). Of 299 terms, 4 are shorter than 5 characters (`demo`, `path`, `mask`, `pair`), and 23 contain non-letters (`**description**`, `order:`, `del_start/del_end`, ...). | "...the first three whitespace-separated docstring tokens of at least five characters, lower-cased with surrounding `.,()`'"` stripped..." |
| R18 | README.md:97-101, 160-171 and the glance tables | recall 100 vs 97 vs 93 on 100 episodes, one seed | CBFR (sample size not stated) | Wilson 95 % intervals: 100/100 → [96.3, 100]; 97/100 → [91.5, 99.0]; 93/100 → [86.2, 96.6]. contexel's and the term-overlap row's intervals overlap. One fixed episode seed (11). | "100 episodes: a 3-point gap is 3 episodes (95 % intervals overlap); one episode seed." |
| R19 | README.md:104-108; site/benchmarks.html:40-44 | "Every benchmark number in this section is generated, or checked against the results" | UNVERIFIABLE (scope) | True for numbers carrying a unit. The rewrite added several quantitative statements that are neither generated nor checked: "most of the contexts ... run over", "not above the term-overlap baseline's", "a few are different functions". All were true when I re-ran them (R5, R9, and 3 keys spanning 5 functions), but they will not be caught if they drift. | Add: "Qualitative statements about the results (for example 'most', 'not above') are not checked." Better: generate them (R5, R9). |
| R20 | README.md:765-770; RESULTS.md:120-125; site/architecture.html:111-114 | "It pairs naturally with ISON ... compact JSON and CSV are not measured here" | CBFR (judgement) | Authorship is now disclosed (good), and the text says any header-plus-rows encoding avoids repeating keys. Suite 6 still compares ISON only with contexel's spaced JSON. The recommendation names only the author's own format. | Add compact JSON and CSV rows to suite 6, or name CSV alongside ISON in the recommendation. |
| R21 | site/index.html:110-115; site/benchmarks.html:108-113 | `class="poor"` on langchain-core recall 30 % / useful 89.7 % and on the llama-index-core and toolz Fill cells | CBFR (judgement) | The prose now says these rows "do not rate the libraries at their own jobs". The styling still grades them visually. R3 and R4 show that the graded cells are largely wiring artifacts. | Drop the best/poor highlighting on the competitor rows, or keep it only on columns that are not by construction. |
| R22 | README_PYPI.md:121-123; site/index.html:78-81 | "an import of about 20 ms" | CBFR (low) | My re-run (7 fresh interpreters, machine under load): contexel median 35.7 ms, toolz 26.7, langchain_core 180.8, llama_index.core 2,424. The ratios match the published ones; the absolute value does not. Load dependence is disclosed. | "about 20 ms on an idle machine (...); it can double under load". |
| R23 | README.md:733-738; site/benchmarks.html:150-157 | "LlamaIndex offers related operations on its node types: ... `PromptHelper` truncation ... and a `ChatMemoryBuffer` token limit" | CBFR | See R1. `PromptHelper.truncate` shortens every text chunk evenly to fit the window ("Truncate text chunks to fit available context window", installed source). It does not drop low-ranked records. The word "truncation" is correct; the implied equivalence to a budget trim is not. | "...`PromptHelper` (shortens every text chunk evenly to fit the context window)..." |
| R24 | README.md:137-142 and parallels ("Other wirings exist ...") | Alternative wirings are listed for toolz and llama-index-core only | CBFR (asymmetry) | langchain-core has nothing listed. `langchain_core.indexing.index` dedupes documents (ingestion-time, needs a vector store and record manager), and R4's sort shows the order effect. I also tested `trim_messages(allow_partial=True)`: it does not help here (still 31 empty contexts), because each record is one line of JSON and the default splitter splits on newlines. | Add: "for langchain-core, a Python sort before `trim_messages` gives 78 % / 6 %; `langchain_core.indexing.index` dedupes documents at ingestion." |
| R25 | README.md:253-256 | "−29% on JSON-heavy records in its synthetic sample ...; the error differs on other records" | CBFR (low) | The direction is disclosed, but not the error on the benchmark's own records. R5's mean 1.08x implies the estimator under-counts these shaped contexts by about 8 to 13 % (the earlier audit reports −3.9 % raw and −12.8 % shaped). | "...on the comparison's shaped CodeSearchNet records the estimator under-counts by about 13 %." |
| R26 | site/benchmarks.html:47-62 (Suite 1) | Timing rows (65,438 records/s; 94.2 vs 94.5 ms; 166.5 vs 436.0 ms) | CBFR (low) | Unlike Suite 2, Suite 1's timings carry no "one run on one machine, varies with load" caveat on the site. | Add the same one-run caveat under Suite 1. |

Verdict counts (rows above): NEW-REGRESSION 2 (R1, R2); MISLEADING 3 (R3, R4, R8); INCORRECT 1 (R11);
OUTDATED 1 (R10); UNVERIFIABLE 2 (R9, R19); CORRECT-BUT-FRAMING-RISK 17 (R5-R7, R12-R18, R20-R26). Total 26.

## 2. Verified as fine (brief)

* **The checker.** `tools/check_benchmark_numbers.py` passes. Every glance, outcome, inflected and footprint number matches COMPARISON.json and RESULTS.json.
* **Native ops.** The definition text matches `opcount.count` and the step lists. The "(in this wiring)" disclosure is accurate, and so is "Whether a step enters library code is detected automatically; which library functions ... are the benchmark author's choices".
* **Column definitions match the code:**
  * Fill = mean `est_tokens(json.dumps(ctx))/1500`;
  * Useful = tokens of FIELDS-projected first occurrences over the total, and an empty context does score 1/1 = 100 %;
  * ms/episode = one strong-signal pass including scoring;
  * import = median of 5 fresh interpreters timing `import <module>`, start-up excluded;
  * Transitive deps = installed closure with markers evaluated and `extra=""`.
* **Dependency counts reproduce:** contexel 0, toolz 0, langchain-core 25, llama-index-core 60.
* **The two signals.** They differ only in the score value, and the hit order is identical (competitors.py:617-646). Columns are equal by construction for score-ignoring rows. Stated correctly.
* **SimilarityPostprocessor cutoff.** The minimum strong score is 11, so the 2.0 cutoff removes nothing under the strong signal. Under the weak signal it removes 6.6 % of the hits (mean share). The source drops a node when `score < cutoff` or the score is None. Stated correctly.
* **LongContextReorder** sorts by score ascending and interleaves to the front and back (installed source). "Score-ordered reorder" is fair.
* **Duplicates.** 13,921 duplicate records. 3 `(path, symbol)` keys span more than one repository, merging 5 distinct functions. "A few" is accurate.
* **Conversion dominates the timed langchain-core and llama-index-core rows** (R8 numbers). The claim is accurate where it is made.
* **`trim_messages`.** The installed docstring says it reduces "a chat history to a specified token or message count". It does not see records inside one message; `allow_partial` does not change this for one-line JSON (tested).
* **`EmbeddingsRedundantFilter`.** Docstring: "Filter that drops redundant documents by comparing their embeddings". Default threshold 0.95. It still exists in langchain-community main (HTTP 200 on the source file).
* **Haystack** (current main source, fetched 2026-11-26):
  * `DocumentJoiner` modes: concatenate (keeps the highest-scored document per id), merge, merge_embeddings, reciprocal_rank_fusion, distribution_based_rank_fusion;
  * `MetaFieldRanker` exists;
  * `LostInTheMiddleRanker`'s `word_count_threshold` "The document that causes the cumulative word count to reach or exceed the threshold is included in full". Accurate.
* **llama-index-core** has `excluded_llm_metadata_keys` on TextNode, `IngestionPipeline` `DocstoreStrategy.DUPLICATES_ONLY`, `PromptHelper.truncate` and `.repack`, and rerankers `LLMRerank` / `SentenceTransformerRerank` with `top_n`.
* **toolz** has `topk` and `accumulate` and no token concept. Accurate ("can express" is fair; the cut itself needs `itertools.takewhile` or a count).
* **Other projects on PyPI and GitHub.** `context-engineering-toolkit` is absent (`pip index versions`: no matching distribution; PyPI JSON 404). keli-wen/context-kit exists ("A minimal toolkit for Context Engineering — Select, Compress, and Persist context with pure functions"), and `ctxeng` 0.1.9 exists on PyPI ("Build perfect LLM context from your Python codebase"; calling it a "context-shaping library" is a slight stretch).
* **"Semantic tools" category text** (LLMLingua compresses, ColBERT retrieves, cross-encoders rerank) is correct. The contract.html wording on model rerankers is fair.
* **Every surface that mentions ISON carries the authorship disclosure** (README x3, README_PYPI, RESULTS, site index, architecture, getting-started).
* **Removed wording is gone.** No published file contains "Compliance", "full marks", "proven" or "Measured, not asserted". The stages.html tracing numbers were removed. `publish.FILES` now covers all six site pages.
* **Links.** The issues link answers HTTP 200; `stages.html#rescore` and README `#language-parity` exist.
* **The inflected-episode text matches the rule and the table** (99/35, 98/98, 96/35, 90/90; examples from `inflection.py`).
* **The proximity-bonus claim is true** (R9), and so is "most contexts run over" (R5). Only their presentation is at issue.

## 3. Could not verify

* **Whether a fresh download reproduces the pinned dataset digest.** I used the existing cache; its digest verified.
* **Idle-machine timings.** My machine was loaded: the absolute values were about 2x the published ones, and the ratios held.
* **The Haystack claims against a tagged 3.x release.** I checked against the `main` source.
* **LLMLingua's runtime behaviour.** I checked the source only.
* **Whether the "strong" signal resembles "the shape a real multi-term search returns".** That is the author's synthetic formula (`distinct*10 + min(total, 9)`).
* **The drift premise.** It is labelled as a premise, which is fine.

## 4. Hostile-reader pass

**As a langchain-core maintainer**

* 31 % of my row's contexts are empty and counted as fully useful (R3).
* "Never reads the score" is your wiring: one `sorted()` gives 78 % (R4). Your hand-written row is allowed Python and my row is not.
* 396 ms is `HumanMessage` construction you chose to do for 14k records (R8 on the index page).
* No alternative wiring is listed for me, while toolz and llama-index-core get one (R24).
* You measured 1.4.9; we are at 1.8.5 (R10).
* The red `poor` cells still grade me (R21).

**As a llama-index-core maintainer**

* You point users to a class we deprecated (R1).
* The timed row runs none of our operations, only a node round trip, and that is undisclosed on the index page (R8).
* The outcome wiring has no projection, dedupe or budget step even though we ship all three. You disclose this, but the table still prints 129x in red.
* The 2.0 cutoff is a no-op under the strong signal (disclosed).
* The note "postprocessors fit no stage" in the published JSON contradicts your own prose (R14).
* The 1,156 ms import of `llama_index.core` is accurate.

**As a toolz maintainer**

* 2/6 and 91.6x are wiring choices. `topk` plus `accumulate` and one `takewhile` gives 81 / 9 recall at fill 0.65 and useful 100 % (my re-run, with Python `sorted`), and with the shared truncate it equals hand-written. "Can express" is disclosed, but the published row is the worst case.
* 1.2.0 is current (R10).

**As a data scientist**

* 100 episodes, one seed, no intervals: the 3-point lead is 3 episodes (R18).
* The queries are lifted from the target's own snippet in order, which favours an in-order proximity bonus (disclosed; R9, R12).
* Budgets are in estimator units, with real overrun up to 20 % (R5).
* Useful % is by construction for any row that uses contexel's fields (disclosed).
* Qualitative claims are not checked (R19).

## 5. Cross-check against the earlier audit (written after sections 1 to 4)

**Earlier findings that are still wrong or only partly fixed**

* **Facts audit F2 / numbers audit:** the 78 % langchain-core recall with strong-ordered input. The rewrite says "never reads the score" but does not give the 78 % (my R4).
* **Numbers audit D4:** empty contexts in 31 of 100 episodes, useful 85.1 % over non-empty contexts. The rewrite mentions that empty contexts happen, but not the count (R3).
* **Facts audit F6 / numbers audit D2:** the cl100k magnitude (6 % compliance, mean about 1,630 tokens). The rewrite says "most" without the number (R5). The site still has "Budgets that hold" (R6), and the index note's "within the budget on average" stays in estimator terms (R7).
* **Numbers audit D1:** the proximity ablation (95 %) and seed sensitivity (seed 11 is the most favourable of ten; 10-seed means 99.5 / 98.4). The rewrite says "not above" with no number and no seed caveat (R9, R18).
* **Numbers audit D10:** the estimator error on the benchmark's own records (−4 % to −13 %) is not stated (R25).
* **Numbers audit B3:** Suite 1 timings on the site still lack the one-run caveat (R26).
* **Facts audit I3 / numbers audit D18:** compact JSON and CSV in suite 6. The earlier audit measured CSV (30) and columnar JSON (31.6) as cheaper per record than the harness ISON (33.5). The rewrite only says they are "not measured" (R20).
* **Facts audit D2:** `langchain_core.messages.utils` imports in about 254 ms against the 88 ms published. The rewrite covers this only generically ("the modules a task uses can cost more").

**Problems the earlier audit introduced or missed, which the rewrite then carried forward**

* **The earlier facts audit proposed `ChatMemoryBuffer`** (F3, N1, N3 proposed wording) without noticing that llama-index-core 0.14.23 marks it deprecated. The rewrite copied it into six places (R1, NEW-REGRESSION).
* **The earlier facts audit's X9 proposed splitting the LLMLingua row** but missed `rank_method` (including `bm25`) and `reorder_context`. The rewrite then wrote "rank: no; rescore(lexical): no" (R2, NEW-REGRESSION).
* **The earlier facts audit's X5 proposed "ship the execution mechanism"** for both Anthropic items, although its own evidence called code-execution-with-MCP a described approach. The rewrite adopted the overstatement (R11).
* **The earlier facts audit rated "fairest comparison" CORRECT (F8).** The numbers audit called it not neutral. I side with the numbers audit (R12).

**Things I found that neither earlier audit raised**

* The index page lacks the operand-conversion disclosure (R8).
* Versions of every compared library are now behind PyPI (R10).
* The PyPI sentence reads as if the term-overlap row does not perform the six operations (R13).
* Residual "prior art" and "improvised" wording and the "postprocessors fit no stage" note in the published JSON (R14).
* The generated-date header is attached to re-rendered prose (R15).
* The README "From source" install line omits the constraints file (R16).
* The query-term construction does not match its own description (R17).
* No alternative wiring is listed for langchain-core, and `allow_partial` does not rescue it (R24).
* `class="poor"` styling remains on the competitor rows (R21).

**Earlier findings now fixed, as verified**

* The Compliance column and "full marks" are removed everywhere.
* Author disclosure and invitation to correct.
* ISON authorship.
* The Haystack row and prose.
* The ColBERT / cross-encoder category error.
* The `trim_messages` and `EmbeddingsRedundantFilter` wording.
* `context-engineering-toolkit` re-dated and other libraries named.
* "proven" → "tested".
* The stages.html fabricated numbers.
* The "How much does it cut?" dead reference.
* "Timing differences are the library's" (README and benchmarks page).
* The ms/episode definition.
* The dedupe "genuine duplicates" wording.
* The constraints file for versions.
* "CI does not re-run".
* The checker now covers all site pages.

## 6. Must fix (ranked)

1. **R1:** replace `ChatMemoryBuffer` (deprecated in the measured version) with `Memory(token_limit=...)` in all six places, and fix "on its node types".
2. **R2:** correct the LLMLingua row: it ranks contexts, BM25 included, and can reorder them.
3. **R3:** disclose that langchain-core's context is empty in 31 of 100 episodes, and that its useful share is 85.1 % over the non-empty ones (or change the scoring).
4. **R4:** say that "never reads the score" is the wiring, and give the 78 % / 6 % result with a Python sort.
5. **R5, R6 and R7:** state the exact-token overrun (94/100, mean 1.08x, max 1.20x), and reword "Budgets that hold" and the index note's "within the budget on average".
6. **R8:** add the conversion-time disclosure to the index page.
7. **R11:** make clear that Anthropic's code execution with MCP is a described approach, not a shipped mechanism.
8. **R9 and R19:** give the proximity-off number (95 %), and either generate the qualitative claims or say that they are not checked.

## 7. Judgement calls (the human decides)

* R10: whether to name the measured versions in every table caption or re-measure on current releases.
* R12: "fairest" against "closest".
* R13: how to present 0/6 for the hand-written rows.
* R14 and R15: whether to clean up the residual wording in the report title and the published JSON notes, and the header date.
* R16 and R17: small consistency and accuracy edits.
* R18: whether to add intervals or a multi-seed mean.
* R20: whether to add CSV and compact-JSON rows to suite 6.
* R21: whether to remove the best/poor styling from the competitor rows.
* R22: how to phrase "about 20 ms".
* R23: how to describe `PromptHelper`.
* R24: whether to list alternative wirings for langchain-core too.
* R25 and R26: whether to add the real-record estimator error and a Suite 1 timing caveat.
* Beyond wording: whether to keep the "library operations only, no Python glue" outcome experiment at all, or to add an expert-wiring row per library reviewed by its maintainers. The current form answers a narrow question that the glance tables visually present as a broad one.
