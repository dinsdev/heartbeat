"""Shared test setup: a fixed-seed Hypothesis profile for CI (CONVENTIONS section 5)."""

import os

from hypothesis import settings

# In CI a Hypothesis failure must be reproducible, so examples come from a fixed
# seed; locally Hypothesis explores freely.
settings.register_profile("ci", derandomize=True)
if os.environ.get("CI"):
    settings.load_profile("ci")
