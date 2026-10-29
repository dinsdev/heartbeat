# Data license

The ECG recordings and beat annotations this project uses come from the MIT-BIH Arrhythmia Database, version 1.0.0, by George Moody and Roger Mark, published on PhysioNet. The database is made available under the Open Data Commons Attribution License v1.0 (ODC-By 1.0): https://opendatacommons.org/licenses/by/1-0/

The MIT license in `LICENSE` covers this repository's code and model weights. It does not cover the database or data derived from it.

## Attribution notice

Contains information from the MIT-BIH Arrhythmia Database (version 1.0.0, PhysioNet), which is made available under the ODC Attribution License v1.0.

## What in this repository derives from the database

None of the database files are committed. The downloader fetches them into `data/`, which is gitignored, and checks each one against a pinned checksum. These derived items carry the notice above when they exist:

- The demo's traces and beat files (`web/public/data/`, built by the rebuild and shipped with the demo, never committed), with an attribution note beside them.
- The parity fixtures in `fixtures/parity/`: a small number of beat windows from DS1 records.
- The trained model in `models/heartbeat-v1/`, whose `NOTICE` file states that the weights are MIT and gives the ODC-By 1.0 section 4.3 notice for the training data.

## Citations

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Engineering in Medicine and Biology 20(3):45-50 (2001).
- Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005). https://doi.org/10.13026/C2F305
- Pollard T, et al. PhysioNet as a global platform for biomedical research. Nature Health (2026). https://doi.org/10.1038/s44360-026-00096-z

PhysioNet's requested citation is rechecked before publishing (PUB-07).
