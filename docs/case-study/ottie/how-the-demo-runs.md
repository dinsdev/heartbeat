---
topic: "How does the Heartbeat demo run in a browser?"
audience: [recruiters, visitors]
sources: [{label: "Heartbeat README", url: "https://github.com/dinsdev/heartbeat/blob/main/README.md"}, {label: "Heartbeat model card", url: "https://github.com/dinsdev/heartbeat/blob/main/docs/MODEL_CARD.md"}]
language: en
approved_on: null
project: heartbeat
---
The demo plays a recording from the test set and labels each beat in the visitor's browser, with the same model file the Python evaluation scored, run by ONNX Runtime in a Web Worker. Parity tests check that the browser and Python agree on shared test beats. The recording it opens on was picked before testing because it has many irregular beats. The model runs on the visitor's own device, so there is no model server.
