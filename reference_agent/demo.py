"""Runnable end-to-end demo of the reference agent.

    python -m reference_agent.demo            # scripted model, no API key
    python -m reference_agent.demo --live     # real model (needs ANTHROPIC_API_KEY)

The scripted plan below is real code that runs in the sandbox and shapes tool
output with contexel before it re-enters context — the same shape every run.
"""
from __future__ import annotations

import os
import sys

from .agent import Agent
from .model import Finish, RunCode, ScriptedClient

TASK = "Find where retry/backoff is implemented and summarise the retry policy."

SCRIPT = [
    RunCode(
        "hits = search_code('backoff')      # @shaped tool — already bounded\n"
        "result = hits\n"
    ),
    RunCode(
        "files = read_files(['src/retry.py', 'src/config.py'])\n"
        "# distil further for just the summary we need\n"
        "result = pipeline([\n"
        "    stage(select, fields=['path', 'content']),\n"
        "    stage(truncate_field, field='content', max_tokens=220),\n"
        "])(files)\n"
    ),
    Finish(
        "retry/backoff lives in src/retry.py as the `retry_backoff` decorator: "
        "exponential backoff (base_delay * 2 ** (attempt - 1)) capped at max_delay, "
        "with optional full jitter and a max_retries ceiling. Defaults are in "
        "src/config.py (5 attempts, 0.2s base, 10s cap, jitter on); "
        "HttpClient.get in src/http_client.py applies it with max_retries=3."
    ),
]


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv

    if "--live" in argv:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("--live needs ANTHROPIC_API_KEY set in the environment.")
            return
        from .model import AnthropicClient

        model = AnthropicClient()
        print("running with a live model\n")
    else:
        model = ScriptedClient(SCRIPT)
        print("running with the scripted model (no API key needed)\n")

    print(f"TASK: {TASK}")
    print("-" * 68)

    agent = Agent(model, budget=6000, max_steps=8)
    result = agent.run(TASK)

    running = 0
    for obs, tr in zip(result.context.observations, result.traces):
        running += obs.tokens
        print(f"\n[step {obs.step}] ran:")
        print("    " + obs.code.strip().replace("\n", "\n    "))
        print(f"  -> {len(obs.records)} records, {obs.tokens} tokens "
              f"(context ~{running}/{result.context.budget})")
        if tr:
            print("  shaping:")
            for line in tr.splitlines():
                print("    " + line)

    print("\n" + "-" * 68)
    print("CONTEXT:", result.context.report())
    print("ANSWER :", result.answer)


if __name__ == "__main__":
    main()
