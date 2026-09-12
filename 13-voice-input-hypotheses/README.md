# 13 — voice-input-hypotheses

_Русская версия: [README.ru.md](README.ru.md)_

**The agent's defense against its own voice channel: treat every name you heard as a hypothesis, verify before you lecture.**

> Voice transcription garbles domain terms — reliably, inventively, and with
> full confidence. An agent that acts on the transcript as fact will lecture
> the user about their own pantry, plan the wrong meal, buy the wrong part.
> This folder: the failure mode, the pattern, and the config.

## The real failure (sanitized)

User (voice): "use the green halapeno, the red one is softer…" — the transcript
said "jalapeño peppers". The assistant launched a confident lecture about fresh
chili varieties. Reality: the user meant two *bottled sauces* from a local shop;
the topic was a marinade recipe calling for one teaspoon — a teaspoon of a
bottled sauce, not a chopped pepper. Cost: trust, plus a wrong recipe plan.
The transcript was wrong in exactly the way transcripts are wrong: plausible
words, impossible meaning.

## The pattern

1. **Hypothesis, not fact.** Any domain term arriving via voice is tagged as
   unverified in the working memory of the turn.
2. **Verify against the user's world first.** Inventory files, recipe lists,
   purchase history, and (for proper nouns) the user's own previous messages
   are the ground truth — not the transcription and not the model's world model.
3. **Disagree out loud, cheaply.** If the term conflicts with ground truth,
   say so in one line and ask — never deliver a confident lecture built on a
   misheard word.
4. **Record the garble.** Each confirmed voice-confusion becomes a one-line
   entry in the role's SOUL ("voice says X → check Y"), so the next occurrence
   is caught in the model's own memory, not by luck.

## Config

```yaml
# per role SOUL, "historical protection" section
voice_pitfalls:
  - transcript "jalapeno/siracha/gochujang" -> bottled sauces, NOT fresh produce
  - transcript "draniki/dranky" -> potato pancakes (local dish)
  - transcript "redmi file" -> README file
  rule: names from voice input are hypotheses; verify against inventory/files before acting
```
