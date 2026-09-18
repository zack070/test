# Case dataset

A larger (109-payment), more realistic dataset for testing your fix
against before submitting. `expected_answer.json` has the correct
answer for this exact dataset (computed independently from
`pipeline/engine.py`, cross-checked by a second, separately-coded
implementation), so you can run your fixed pipeline against it and
compare directly:

```
python3 pipeline/engine.py data/case /tmp/case_output.json
```

This is a practice dataset, not the graded one -- grading runs your
fixed `engine.py` against two different sealed datasets you never see.
A fix that happens to match this dataset's numbers through some
shortcut specific to it (rather than a genuine fix to the underlying
rule logic) will not generalize to those.
