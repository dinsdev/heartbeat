---
topic: "How was Heartbeat tested, and what did the test show?"
audience: [recruiters, visitors]
sources: [{label: "Heartbeat model card", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/MODEL_CARD.md"}, {label: "Heartbeat test log", url: "https://github.com/dinsdev/heartbeat/blob/main/results/test_runs.jsonl"}]
language: en
approved_on: null
project: heartbeat
---
Dinesh wrote down what would be reported before the test, including the sentence the page would use for each possible outcome. The model was then fixed by a committed freeze record, and the sealed test set was scored once, with the run written to an append-only log. The outcome was no clear difference between the CNN and the logistic-regression baseline, and the CNN still ships, as the plan said it would. The case study page has the numbers, with their intervals.
