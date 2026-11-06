---
topic: "Why does Heartbeat keep patients apart when it splits the data?"
audience: [recruiters, visitors]
sources: [{label: "Heartbeat case study outline", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/CASE_STUDY_OUTLINE.md"}, {label: "Heartbeat data card", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/DATA_CARD.md"}]
language: en
approved_on: null
project: heartbeat
---
If heartbeats are split at random, the same person ends up on both sides of the split, and a model can score well by recognizing the person. Heartbeat shows this on its training data, with the same model split both ways, and credits de Chazal and colleagues' Table VI as the precedent. It also removes a leak in the standard split: Records 201 and 202 come from the same person and sit on opposite sides, so record 202 is left out everywhere. The case study page has the numbers.
