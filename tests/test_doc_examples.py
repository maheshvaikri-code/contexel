"""The README's runnable examples are executed from the README itself (brief
AC 34): every ```python block in the section is run and its printed output must
equal the ```text block that follows it, so documentation cannot drift from
behavior. Slices 4 and 5 add their sections to SECTIONS."""
import contextlib
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
FENCE = re.compile("```(python|text)" + NL + "(.*?)```", re.S)

#: (README heading, number of runnable examples the section must contain)
SECTIONS = [("### Errors and strict mode", 2)]

with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
    README = fh.read()


def _section(heading):
    start = README.index(heading)
    end = README.find(NL + "## ", start)
    return README[start:end if end != -1 else len(README)]


def _examples(heading):
    blocks = FENCE.findall(_section(heading))
    pairs = []
    for i, (lang, body) in enumerate(blocks):
        if lang == "python":
            assert i + 1 < len(blocks) and blocks[i + 1][0] == "text", (
                "every python example is followed by its expected output")
            pairs.append((body, blocks[i + 1][1]))
    return pairs


@pytest.mark.parametrize("heading, count", SECTIONS)
def test_each_documented_section_has_its_runnable_examples(heading, count):
    assert len(_examples(heading)) == count


CASES = [(h, i) for h, n in SECTIONS for i in range(n)]


@pytest.mark.parametrize("heading, index", CASES)
def test_readme_example_prints_what_the_readme_shows(heading, index):
    source, expected = _examples(heading)[index]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(source, f"README:{heading}#{index}", "exec"), {"__name__": "__readme__"})
    assert out.getvalue().strip() == expected.strip()
