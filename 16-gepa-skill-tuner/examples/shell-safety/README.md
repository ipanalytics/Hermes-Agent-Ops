# Example — shell-safety classifier

The task set behind module 15's `bash_guard` rules, expressed as a prompt-optimization task:
29 labelled commands (including the quote-obfuscated and decoder-piped evasions), metric =
exact match on SAFE/UNSAFE.

```bash
bash run.sh                       # 60 metric calls, writes report.json
MAX_CALLS=150 bash run.sh --write # write the improved prompt back over seed_prompt.txt
```

**Read the result honestly.** With a strong task model this set is already solved by the seed
prompt (our run: seed ≈ 1.0 on the validation split, three candidates explored, no change
survived). That is the correct outcome and the reason the wrapper prints
`No prompt change survived validation` instead of a fake improvement: prompt optimization
only pays where the prompt, not the model, is the bottleneck. Swap in a weaker task LM
(`--task-lm openrouter/<small-model>`) or a harder labelled set and the same command produces
a real diff.
