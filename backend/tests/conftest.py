"""Test-wide settings: the background sweep loop is off (tests call run_sweep explicitly)."""

import os

os.environ["SWEEP_ENABLED"] = "false"
