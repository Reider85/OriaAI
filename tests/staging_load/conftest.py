"""Gate the F-1 staging-load suite behind an explicit opt-in.

Plain `pytest` must NOT run heavy staging-load tests accidentally. Set
RUN_STAGING_LOAD=1 (as the F-4 nightly job does) to collect them.
"""

import os

if os.getenv("RUN_STAGING_LOAD") != "1":
    collect_ignore = ["test_cancel_latency.py"]
