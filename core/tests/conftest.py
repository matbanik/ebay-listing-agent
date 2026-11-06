"""Keep tests off any real workspace: EBAY_WORKSPACE is read when the tools are imported."""

import os

os.environ.pop("EBAY_WORKSPACE", None)
