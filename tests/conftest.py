"""Keeps the tests away from the user's real settings and cache."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="infinifind-tests-")
os.environ["INFINIFIND_DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["INFINIFIND_CACHE_DIR"] = os.path.join(_TMP, "cache")
os.environ["INFINIFIND_NO_KEYRING"] = "1"  # tests that need a keychain use a fake one
