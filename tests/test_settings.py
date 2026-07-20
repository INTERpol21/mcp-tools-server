"""Config defaults — guards the seeded data directory resolution."""

from __future__ import annotations

from app.core.settings import _default_data_dir


def test_default_data_dir_is_the_seeded_repo_directory():
    """The default must resolve to the repo-root data/ that actually holds seed.

    Regression: the default used to be app/data (only a stale demo.db), so a bare
    `python -m app.server` (DATA_DIR unset) broke search_web ("index not found")
    and registered zero docs:// resources. Assert the seed files are all there.
    """
    data_dir = _default_data_dir()
    assert data_dir.name == "data"
    assert (data_dir / "search_index.json").exists()
    assert (data_dir / "docs").is_dir()
