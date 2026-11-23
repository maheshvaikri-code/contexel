# The `stem` rule table

`rescore(..., match="stem")` reduces every word of the query and of the text to
a stem before it counts, so `parse`, `parses`, `parsed` and `parsing` are one
term. This page is the complete, frozen specification of that reduction
([ADR-006](adr/006-rescore-matching-modes.md)). Python (`contexel/stem.py`),
TypeScript (`ts/src/stem.ts`) and C# (`csharp/Contexel/Stem.cs`) implement it
exactly, and `parity/vectors.json` holds well over a hundred word-to-stem pairs
that all three must reproduce.

It is a **small English suffix stemmer**, not a lemmatizer and not Porter. It
does not know irregular forms (`ran`, `mice`), other languages, or meaning
(`configure` and `config` stay apart). It is frozen: a future improvement ships
under a new `match` name, never by editing these rules, so a policy that says
`match="stem"` means the same thing for as long as the name exists.

## Input

One word at a time: a token the `rescore` word pattern found (letters and
digits; underscores split words), already lower-cased. Lengths are counted in
**code points**, so an astral letter counts once in every language. The rules
are case-sensitive: an upper-case suffix is not recognized (`rescore`
lower-cases first, so it never meets one). The function never raises, accepts
any string including the empty one, and never returns a longer word.

## The rules, in order

0. **Short words.** A word of 3 code points or fewer is returned unchanged.
1. **Plurals.** The first of these that applies, and only one:
   1. the word ends with `sses`: drop the last two letters (`glasses` to `glass`);
   2. it ends with `ies` and has more than 4 code points: replace `ies` with `y` (`queries` to `query`);
   3. it ends with `ied` and has more than 4 code points: replace `ied` with `y` (`queried` to `query`);
   4. it ends with `s` but not with `ss`, `us` or `is`: drop the `s` (`tests` to `test`).

   When a rule's length condition fails the next rule is tried, so `ties` (four
   letters) reaches rule 4 and becomes `tie`.
2. **`ing` and `ed`.** If the word now ends with `ing`, the suffix is `ing`;
   otherwise, if it ends with `ed`, the suffix is `ed`; otherwise there is none.
   Only that one suffix is considered, and only once. Strip it **only if** the
   remaining base has at least 3 code points **and** contains at least one of
   `a e i o u y`. If it was stripped and the base ends in a doubled letter from
   `b c d f g h j k m n p q r t v w x`, drop one of the two (`running` to `run`;
   `falling` stays `fall` because `l` is not on the list).
3. **Final `e`.** If the word now ends with `e` and has more than 3 code
   points, drop the `e` (`parse` to `pars`).

That is the whole algorithm.

## Worked examples

Every row of the tables below is run against the stemmer by
`tests/test_stem.py`, so this page cannot drift from the code.

### Plurals

| word | stem |
|---|---|
| `glasses` | `glass` |
| `passes` | `pass` |
| `queries` | `query` |
| `studies` | `study` |
| `queried` | `query` |
| `studied` | `study` |
| `tests` | `test` |
| `values` | `valu` |
| `caches` | `cach` |
| `ties` | `tie` |
| `lies` | `lie` |
| `tied` | `tied` |
| `class` | `class` |
| `status` | `status` |
| `analysis` | `analysis` |
| `bus` | `bus` |
| `gas` | `gas` |

### `ing` and `ed`

| word | stem |
|---|---|
| `parsing` | `pars` |
| `parsed` | `pars` |
| `testing` | `test` |
| `tested` | `test` |
| `running` | `run` |
| `stopped` | `stop` |
| `falling` | `fall` |
| `passed` | `pass` |
| `loading` | `load` |
| `loaded` | `load` |
| `feeding` | `feed` |
| `need` | `need` |
| `string` | `string` |
| `spring` | `spring` |
| `sing` | `sing` |
| `king` | `king` |
| `bed` | `bed` |

### Final `e`

| word | stem |
|---|---|
| `value` | `valu` |
| `file` | `fil` |
| `code` | `cod` |
| `parse` | `pars` |
| `cache` | `cach` |
| `use` | `use` |
| `are` | `are` |
| `one` | `one` |
| `type` | `typ` |
| `rule` | `rul` |

### Several rules in one word

| word | stem |
|---|---|
| `parses` | `pars` |
| `indexes` | `index` |
| `matches` | `match` |
| `stopping` | `stop` |
| `configured` | `configur` |
| `configuring` | `configur` |
| `requests` | `request` |
| `returning` | `return` |

## Known limits

These are the price of a rule set small enough to repeat exactly in three
languages. They are documented, not bugs, and changing any of them is a new
mode, not an edit.

| word | stem |
|---|---|
| `configure` | `configur` |
| `config` | `config` |
| `speed` | `spe` |
| `news` | `new` |
| `using` | `using` |
| `series` | `sery` |
| `species` | `specy` |
| `bias` | `bia` |
| `ran` | `ran` |
| `mice` | `mic` |
| `adds` | `add` |
| `added` | `ad` |
| `adding` | `ad` |
| `egged` | `eg` |
| `died` | `died` |
| `dies` | `die` |

- `configure` and `config` do not meet: the stem is a spelling, not a meaning.
- A stem is not a word: `value` becomes `valu`, which is fine because the query
  is reduced the same way.
- A word that ends in `ed` or `ing` by accident is cut when the base is long
  enough and has a vowel (`speed` to `spe`); `using` is left alone only because
  its base, `us`, is shorter than three letters.
- Undoubling runs after the three-code-point test on the base, so a stem can be
  two letters (`added` to `ad`) and a word and its inflections can split
  (`add`/`adds` stay, `added`/`adding` become `ad`; `die`/`dies` stay, `died` is
  unchanged).
- English only. Other languages are matched with `match="word"`.

## Where it applies

Only `rescore(match="stem")`. The query is tokenized and each token stemmed; the
distinct stems, in first-occurrence order, are the terms. The text is
tokenized the same way and every word whose stem is a term counts as one
occurrence of that term. Scoring, the inverse document frequency, the proximity
bonus and the rounding are the ones of `match="word"`; a position is the start
of the word, counted in code points.
