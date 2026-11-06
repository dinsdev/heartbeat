---
topic: "Where does Heartbeat fall short?"
audience: [recruiters, visitors]
sources: [{label: "Heartbeat model card", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/MODEL_CARD.md"}, {label: "Heartbeat data card", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/DATA_CARD.md"}]
language: en
approved_on: null
project: heartbeat
---
Beat locations come from the expert annotations, so the results assume every beat has already been found. The model reads one lead. The F class comes almost entirely from one patient on each side, record 232 drives the S result, and calibrated probabilities are fragile across patients. A label shows one beat late, because the model reads the gap to the next beat. The database was not built to show how common arrhythmias are, so its results say nothing about that.
