"""文件型持久化。"""

from __future__ import annotations

from coke.store.journal import JsonlJournal
from coke.store.jsonfile import JsonStore


def test_json_store_write_read_remove(tmp_path):
    store = JsonStore(str(tmp_path / "docs"))
    store.write("platform_state", {"operations": 3})
    assert store.exists("platform_state")
    assert store.read("platform_state") == {"operations": 3}
    assert store.list_ids() == ["platform_state"]
    assert store.remove("platform_state") is True
    assert store.remove("platform_state") is False
    assert store.read("platform_state") is None


def test_json_store_path_and_root(tmp_path):
    store = JsonStore(str(tmp_path / "docs"))
    assert store.root.endswith("docs")
    assert store.path_of("x").endswith("x.json")


def test_journal_rolls_segments(tmp_path):
    journal = JsonlJournal(str(tmp_path / "journal"), "audit", segment_limit=2)
    for index in range(5):
        journal.append({"index": index})
    assert journal.count() == 5
    assert journal.active_segment() == 2
    assert len(journal.segments()) == 3
    assert [item["index"] for item in journal.read_segment(0)] == [0, 1]
    assert [item["index"] for item in journal.read_all()] == [0, 1, 2, 3, 4]
    assert journal.topic == "audit"
