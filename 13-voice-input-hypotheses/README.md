# 13 — voice-input-hypotheses

_Russian version: [README.ru.md](README.ru.md)_

The defense against my own voice channel: every name that comes in by voice is a hypothesis, and I verify it before any lecture.

> Voice transcription garbles domain terms — reliably, inventively, and with full confidence. An agent that takes the transcript at face value will lecture me about my own pantry, plan the wrong meal, buy the wrong part.

## Hermes, in one paragraph

Hermes is the AI agent that lives on my server. He listens to me through a voice channel as well as reading text: the voice side runs through an automatic speech recogniser (the ASR pipeline that turns spoken audio into written text — the *transcript*) and then into the same agent that handles typed input. The transcript is what the rest of the agent sees. This folder is what stops the agent from mistaking the transcript for the truth.

## What "hypothesis" means

A *hypothesis* is a guess that has not been checked yet. For text input, the heuristic is usually fine: if I type "use the green jalapeño", that is what I mean, typos aside. For voice input, the same sentence can come out as "use the green halapeno" — which the agent reads as "jalapeño" with high confidence. The literal transcript is plausible; the meaning is wrong. Treating the literal transcript as fact means treating a guess as a fact, and the rest of the turn inherits that error.

The rule I landed on: anything that arrives through the voice channel is a hypothesis until I have checked it against my own world — the inventory files, the recipe notes, the purchase history, my own past messages. Not against what the model happens to know about peppers, sauces or files in the abstract world.

## The real failure (sanitised)

The exact transcript line that started this folder: "use the green halapeno, the red one is softer…". The ASR happily turned that into "jalapeño peppers". The assistant produced a textbook paragraph about the difference between green and red jalapeño varieties — heat, ripeness, the cuisine they belong to. Confident. Fluent. Completely off.

What I actually meant: two *bottled sauces* from a small shop around the block. The recipe was a marinade needing one teaspoon of one of those sauces — a teaspoon of bottled sauce, not a chopped pepper. The lecture was about the wrong ingredient, in the wrong form, from the wrong shelf. The cost was not a price; it was trust — and an unusable marinade plan. The transcript was wrong in exactly the way transcripts are wrong: plausible words, impossible meaning.

A few weeks later the same pattern hit on "redmi file" (a *README* file), and on "draniki" (a local potato-pancake dish that the transcript kept rendering as "dranky"). One handler cannot do better than the transcript by itself; the transcript is what it is.

## The pattern

1. **Hypothesis, not fact.** Any domain term arriving via voice is tagged as unverified in the working memory of the turn. The tag follows the term: not "jalapeño", but "jalapeño [unverified voice]".
2. **Verify against my world first.** I treat inventory files, recipe lists, purchase history and — for proper nouns — my own earlier messages as the ground truth. Not the transcript, and not what the model happens to know about the world. If the term is in the inventory under a different name, that other name is what gets used.
3. **Disagree out loud, cheaply.** If the term conflicts with ground truth, I say so in one line and ask. No confident lectures built on a misheard word. The cost of one short clarification is much smaller than the cost of a confident wrong answer — a recipe, a part number, a name.
4. **Record the garble.** Every confirmed voice-confusion becomes a one-line entry in the role's *SOUL* — the per-role configuration file that lists the role's voice pitfalls and standing rules — under "voice says X → check Y". The next occurrence gets caught by memory, not by luck. The mistake has to be expensive only once.

## The config

The pattern lives in the role's SOUL file as a `voice_pitfalls:` block under "historical protection":

```yaml
# per role SOUL, "historical protection" section
voice_pitfalls:
  - transcript "jalapeno/siracha/gochujang" -> bottled sauces, NOT fresh produce
  - transcript "draniki/dranky" -> potato pancakes (local dish)
  - transcript "redmi file" -> README file
  rule: names from voice input are hypotheses; verify against inventory/files before acting
```

Each line is one past failure. The rule at the bottom is the one I want the agent to apply even when no specific entry matches: every voice-derived name has to be checked. The block is read every time the role loads; that is why I keep it short — a long list of pitfalls is the same thing as no fallback.

## What the rule is not

It is not a list of words to auto-correct. The transcript is the transcript; it gets stored verbatim so I can debug from it later. The rule is about how the agent *responds* to the transcript — verify, then act — not about rewriting what came in.

It is also not a ban on voice. Voice is still the fastest way to dictate a recipe step or a part number. The cost is the verification step, and that step is cheap if I keep the inventory tidy.