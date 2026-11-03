# Vision

*Fupan is a provisional name. This document describes intent, not shipped
features. For current status see the README; for sequencing see the roadmap.*

## One sentence

**Fupan turns your games into a diagnosis and a training plan.**

Fupan is a Go (Weiqi / Baduk) project. Its name comes from 复盘, the tradition of
replaying a finished game to find where it was won and lost.

## The problem

Strong engines made one question easy: *which move in this game lost the most
points?* Open-source tools such as KaTrain and Lizzie answer it well for a
single game. Players who want to improve need answers to different questions:

- *Where am I actually weak?* Across many games, not just this one.
- *Why was this move bad?* In terms a player can learn from, without invented
  reasoning.
- *What should I practice, and did the practice work?*
- *Which of these mistakes matter at my level?*

A single-game list of point losses does not answer them. A pile of reviewed
games does not answer them either unless something aggregates, explains and
turns the results into practice.

## Target users

1. **Primary: the owner.** An amateur 4-dan who knows how KataGo works and will
   use Fupan on their own games first. Every feature must be useful to this
   user before it is generalized.
2. **Serious amateur players, roughly mid-kyu to high-dan,** who play regularly
   online or over the board, keep SGF records, and want structured improvement.
3. **Later: teachers and study groups** who want to see a student's patterns.
   Not a design target until the first two groups are served.

East Asian users are a first-class audience: Chinese is a primary interface and
explanation language, with English alongside; Japanese and Korean terminology
should be supportable by the glossary design.

## Four pillars

### 1. From a game to a player profile

Aggregate analysed games (tens to hundreds) into a profile:

- loss distribution by **game phase** (opening, middle game, endgame) and by
  **situation type** (life and death, invasion, ko fights, endgame, and others
  defined in the architecture);
- **trends over time**, with sample sizes and **confidence intervals**, so that
  a change is distinguishable from noise;
- the profile answers "where am I weak?", not only "which move was wrong?".

Phase and situation labels come from versioned, deterministic, engine-backed
classifiers whose accuracy is measured on labelled examples before their
statistics are shown as anything other than experimental.

### 2. Explanations with reasons

Explanations are assembled from deterministic analysis:

- the engine's principal variation for the better move and the played move;
- score change and winrate change, with stated perspective and units;
- ownership change, and **which group's status changed** (for example "the
  seven black stones on the lower side went from alive to dead");
- phase and situation context.

They are written in Chinese and English with standard Go terminology from a
maintained glossary. If an LLM is later used to polish wording, the structured
analysis is its only source, and output that introduces a coordinate, number
or variation not present in the facts is rejected.

### 3. Closed-loop training

**Review → diagnose → practise → measure again.**

- Positions where the player lost significant points become exercises
  automatically, with the engine's acceptable answers precomputed.
- A spaced-repetition scheduler decides when each exercise returns.
- Progress is measured twice: on the exercises themselves, and on whether the
  same weakness appears less often in new games.

### 4. Calibrated to the player's strength

Thresholds and explanation emphasis adapt to level. A 10-kyu player should not
be told about a one-point endgame inaccuracy while a group died elsewhere; a
dan player may want exactly that inaccuracy. Calibration settings are product
choices to be tuned with real users, and are presented as such.

## Principles

- **Never invent.** No fabricated scores, variations or Go reasoning.
- **Evidence is reproducible.** Every result records the engine, model, settings
  and metric definitions that produced it.
- **Honest uncertainty.** Show sample size, coverage and confidence; label
  experimental statistics.
- **Quiet, precise design.** Restraint in the spirit of Apple and LoveFrom:
  generous whitespace, a restrained palette, careful alignment, a serif display
  face in the Baskerville family for headings, balanced Chinese and Latin
  typography. Interactive visualisations (a clickable loss timeline, an
  explorable profile) over static tables.

## Non-goals

- Not a playing engine and not a bot.
- No neural-network training. Fupan uses KataGo and its published networks.
- Not a board or SGF editor competing with Sabaki or KaTrain.
- No scraping of online platforms. Future platform imports use public APIs and
  respect each platform's terms.

## How Fupan differs from existing tools

The comparison below is limited to capabilities we are confident about; it will
be re-checked before any public comparison is published.

| Tool | What it does well | Where Fupan differs |
| --- | --- | --- |
| KataGo | The analysis engine itself | Fupan is a consumer of KataGo, not an engine |
| KaTrain | Single-game KataGo review, point-loss display, teaching play | Fupan focuses on multi-game diagnosis, explanation and practice; it does not compete on board UI or play modes |
| Lizzie / LizzieYzy | Interactive engine analysis with winrate graphs | Same as above: Fupan's unit of value is the player, not the position |
| Sabaki | SGF editing and engine attachment | Fupan is not an editor |
| Online platforms' AI reviews and commercial review services | Convenient per-game reviews inside a platform | Fupan is platform-independent, explains with traceable evidence, and closes the loop with practice; detailed feature comparisons are not claimed here |

## What success looks like

The first milestone of success is personal: the owner reviews their own recent
games in Fupan, recognises the diagnosis as true, practises the generated
exercises, and sees a measurable change in later games — with the
uncertainty of that measurement stated honestly.
