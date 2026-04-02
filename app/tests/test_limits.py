import pytest

from app.services.sandbox.limits import enforce_patch_limits


def test_diff_limit_accepts_small_patch() -> None:
    diff_text = """diff --git a/app/a.py b/app/a.py
--- a/app/a.py
+++ b/app/a.py
@@
-return 1
+return 2
"""
    stats = enforce_patch_limits(diff_text, ["app/"], ["migrations/"], 5, 10)
    assert stats.files_changed_count == 1
    assert stats.diff_line_count == 2


def test_diff_limit_rejects_blocked_path() -> None:
    diff_text = """diff --git a/migrations/a.py b/migrations/a.py
--- a/migrations/a.py
+++ b/migrations/a.py
@@
-x=1
+x=2
"""
    with pytest.raises(ValueError, match="path_not_allowed"):
        enforce_patch_limits(diff_text, ["app/"], ["migrations/"], 5, 10)
