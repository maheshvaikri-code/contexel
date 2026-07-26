# The Context Contract

*Deterministic context assembly for spec-driven agentic coding, with `contexel`.*

---

Spec-driven development made the specification a first-class, versioned artifact and a contract for what an agent should build. But the context an implementing agent actually reasons over — the search results, file reads, and test output it pulls from the repo at runtime — is governed by no contract at all. It is assembled ad hoc and reshaped differently on every run, and that uncontrolled context is the hidden variable that quietly undermines SDD's reproducibility promise.

This thesis argues that the missing piece is a **context contract**: a deterministic, versioned policy for how the repo's tool outputs become the agent's context. `contexel` is a minimal, adoptable implementation of that idea — not a spec tool, but the deterministic floor beneath the agent that implements the spec.

## 1. The promise of spec-driven development, and the variable it leaves loose

The premise of SDD is clean: the specification is the durable source of truth, code is regenerable from it, the spec is the contract, and the same spec should yield consistent results. Underneath that promise sits an unstated assumption — that an agent's behavior is a function of the spec.

In practice it is not. Behavior is a function of the spec *and the context the agent assembled from the repo*. The spec is written, typed, reviewed, and versioned. The context is improvised at runtime and thrown away. Two runs against an identical spec can see materially different contexts and therefore produce materially different implementations — not because the spec changed, but because the context did. SDD pinned the contract and left the input loose.

## 2. Why context is the leak, and why it is worse in coding

Coding agents are unusually tool-heavy. They lean on codebase and semantic search, file reads, symbol and reference lookup, test and CI output, and git history. These return large, structured payloads — lists of records — that vastly exceed the context window and must be compressed before the model reads them.

The prevailing mechanism for that compression is the model writing throwaway code to reshape tool output, run by run. That mechanism is nondeterministic by construction: it re-derives the field selection, the truncation, and the trimming slightly differently each time, mishandles edge cases unevenly, and silently varies what survives into context. So the very pipe that feeds the agent is itself a drift source. In a methodology whose entire selling point is reproducibility, the feed is unreproducible.

## 3. Three axes of repetition where the drift compounds

The cost is not a one-off. It compounds along three axes, because a coding agent works the same repository again and again.

**Iteration to iteration — the fix loop.** Implement, run the tests that encode the acceptance criteria, read the failures, fix, repeat. The test output grows and re-noises on every pass. If its shaping wobbles, the agent's view of "what is still failing" wobbles with it, and the loop can thrash on a moving target instead of converging.

**Run to run — re-running a story.** Re-run the same spec on the same repo and you expect the same behavior. Ad hoc reshaping breaks that even when nothing else has changed, because the context the model sees is reconstructed from scratch each time.

**Story to story — the same repo, many times.** A backlog of stories all hit one codebase. You want the agent's *treatment* of that codebase — how search results and file reads become context — to be uniform across every story, so that behavior is a function of the story and not of how the model happened to compress things that day.

In all three, the quantity you want held constant is the *policy* by which raw repo output becomes context. Today nothing holds it constant.

## 4. contexel as a context contract

The reframe is simple. SDD's discipline is to make intent an explicit, typed, versioned artifact. Apply the same discipline to context assembly.

A `contexel` pipeline is a deterministic function from raw tool output to distilled context. Write it once, version it in the repo beside the spec, and apply it at every tool boundary. Context assembly is now governed by a reviewed artifact — a context contract — exactly as the build is governed by the spec.

```python
# project_context.py — one context policy for this repo, versioned beside the spec
from contexel import select, dedupe, truncate_field, rank, trim_to_budget, pipeline, stage

CODE_SEARCH = pipeline([
    stage(select, fields=["path", "line", "symbol", "snippet", "score"]),
    stage(dedupe, key=["path", "line"]),
    stage(truncate_field, field="snippet", max_tokens=60),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=2000),
])

TEST_REPORT = pipeline([ ... ])   # the same lens on every test run
```

Two guarantees make this a contract rather than a convenience. First, **deterministic shaping**: identical input records through the same pipeline yield byte-identical output, so reshaping stops being a variable. Second, **uniform policy**: the same pipeline applied across iterations, runs, and stories means the repo is always seen through one lens. And it is inspectable — `trace()` records what each stage did, so the contract is not a black box; you can see, for any run, exactly how the repo became context.

One distinction deserves to be stated plainly, because it is the same honesty SDD demands of itself. A context contract removes two kinds of tokens, and they are not equivalent. `select` and `dedupe` remove genuine redundancy — unused fields, true duplicates — losslessly; nothing of value is lost. `truncate_field` and `trim_to_budget` discard detail and low-ranked records to hit limits you set; that is a deliberate completeness-for-budget trade. A good context contract makes both deterministic, and it makes the second *visible* through the trace, so what you chose to drop is an explicit, reviewable decision rather than a silent one — the same standard a spec holds itself to.

## 5. contexel across the SDD lifecycle

The lifecycle runs spec → plan → tasks → implement → check against criteria, with the fix loop nested inside implementation. `contexel` is the deterministic shaping step at each tool boundary and between phases.

During implementation, codebase search is shaped through the contract on every call — applied inside the tool itself, so the agent simply calls `search_code(...)` and the model never writes the reshaping, never varies it, and the same refactor sees the same lens each run. Between phases, the artifact each phase emits — task lists, plan items, decisions resurfaced from search — is record-shaped, and the same pipelines keep those handoffs consistent. When context must be drawn from several sources at once — code search, design docs, prior test runs — `merge` normalizes their differing schemas into one shape before the agent reasons over them, so even multi-source assembly is governed rather than improvised.

## 6. The fix loop, worked

The inner loop is acceptance-criteria-driven, which makes it the sharpest fit. The test report is shaped so that each failure is tied back to the criterion it violates:

```python
from contexel import select, rank, truncate_field, trim_to_budget

def failing_tests(report) -> list[dict]:
    cases = report.results          # {id, status, criterion, traceback (long), duration, ...}
    fails = [c for c in cases if c["status"] == "failed"]
    r = select(fails, ["id", "criterion", "traceback"])   # keep the link to the criterion
    r = truncate_field(r, "traceback", max_tokens=80)      # clip the stack
    r = rank(r, by="criterion", desc=False)                # group by the criterion violated
    return trim_to_budget(r, max_tokens=1500)
```

Each iteration the agent sees a consistent, high-signal view: what is still failing, grouped by which numbered criterion it breaks — not an ever-growing wall of logs. The loop converges on stable signal instead of thrashing on shifting context. For a spec written as numbered acceptance criteria, the shaping literally re-projects the test output back onto the spec's own structure, closing the loop between contract and feedback.

## 7. What contexel does not do

Naming the boundaries is not a hedge; it is the same discipline, and an honest thesis owes it.

**It is not a spec tool.** It does not author, parse, lint, or validate specs, and it does nothing for the quality of what you specify. It is not a step in the spec workflow — it is the substrate under the agent that executes the workflow.

**It pins shaping, not inputs.** If your retrieval or search is itself nondeterministic, or the repo state changed between runs, `contexel` faithfully shapes whatever it is handed; it cannot make varying inputs identical. True run-to-run identity also requires deterministic retrieval and a pinned repo state. `contexel` removes the largest *controllable* drift source — it is necessary, not sufficient.

**It is stateless, not memory.** It holds nothing between calls. If "context intact across runs" must include carrying decisions or accumulated state forward, that is a memory layer — a different primitive. `contexel` makes each run's context consistent; it does not make it persistent.

A context contract that overpromised would be as corrosive to SDD as a spec that did.

## 8. The case: compounding value and a debuggable failure mode

Because a backlog reworks the same repository repeatedly, a context contract is amortized. Write the lens once and every story and every run inherits it; the lossless savings and the reliability compound across the backlog instead of being re-paid per task.

The failure mode also changes character. When an implementation misses something, the trace lets you ask a precise question — did the relevant context even reach the model? — and turns a black-box miss into an inspectable shaping decision you can adjust in one versioned place. In a spec-driven shop, that is the difference between debugging the agent and debugging the contract, and only the second is a tractable, repeatable engineering activity.

## 9. Conclusion: context assembly as a first-class artifact

SDD's real move was epistemic. It took something that had lived implicitly in developers' heads — intent and acceptance — and made it explicit, typed, versioned, and reviewable. The argument here is that context assembly deserves the same promotion. The agent's view of the repo is currently improvised on every run; it should instead be a reviewed artifact that lives beside the spec and changes only by intention.

`contexel` is a deliberately small way to do that: plain functions over the records your tools already return, riding the pattern that already won — code as the transform substrate — rather than asking anyone to adopt a new primitive. The spec says what to build. The context contract says what the builder is allowed to see. Spec-driven development gave you the first. This is the case for writing the second.
