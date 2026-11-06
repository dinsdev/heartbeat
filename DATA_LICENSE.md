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

- Moody, G., & Mark, R. (2005). MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet. RRID:SCR_007345. https://doi.org/10.13026/C2F305
- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. IEEE Eng in Med and Biol 20(3):45-50 (May-June 2001). PMID: 11446209.
- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. Nature Health. https://doi.org/10.1038/s44360-026-00096-z. Available from: https://pmc.ncbi.nlm.nih.gov/articles/PMC13641116/

These are the citations PhysioNet's MIT-BIH page asks for, rechecked against that page on 2026-11-05 (PUB-07), along with the license it names: ODC-By 1.0.
