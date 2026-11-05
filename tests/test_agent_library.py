"""agent.py: the library agent's scope, its safe action plan, and applying a confirmed plan."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from textfold import agent, library, store


class AgentLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(store, "DATA", Path(self.tmp.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        for pid, title in (("md-test-0001", "Graph methods"), ("md-test-0002", "Graph evidence")):
            d = store.pdir(pid)
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"title": title}), encoding="utf-8")
            (d / "source.html").write_text("<p>A paragraph.</p>", encoding="utf-8")

    def test_a_topic_sees_only_its_own_papers_however_deep(self):
        top = library.change({"op": "new", "name": "Graph reading", "papers": ["md-test-0001"]})["folders"][-1]
        sub = library.change({"op": "new", "name": "Evidence", "parent": top["id"], "papers": ["md-test-0002"]})["folders"][-1]
        data = agent.context("topic", top["id"])
        self.assertEqual({p["id"] for p in data["papers"]}, {"md-test-0001", "md-test-0002"})
        self.assertEqual(data["topic"]["name"], "Graph reading")
        self.assertEqual(agent.context("library")["topic"], None)
        self.assertEqual(sub["parent"], top["id"])
        with self.assertRaises(ValueError):
            agent.context("topic", sub["id"])   # only a top-level folder has a topic page

    def test_actions_are_limited_to_folders_names_and_moves(self):
        top = library.change({"op": "new", "name": "Reading"})["folders"][-1]
        papers = agent._rows()
        folders = library.folders()["folders"]
        made = agent.prepare_actions([
            {"op": "new_folder", "name": "Graphs", "papers": ["md-test-0001"]},
            {"op": "move_papers", "papers": ["md-test-0002"], "folder": top["id"]},
            {"op": "rename_paper", "paper": "md-test-0002", "name": "Evidence, renamed"},
            {"op": "delete", "paper": "md-test-0001"},
            {"op": "move_papers", "papers": ["md-does-not-exist"], "folder": top["id"]},
        ], papers, folders)
        self.assertEqual([a["op"] for a in made], ["new_folder", "move_papers", "rename_paper"])
        self.assertEqual(made[0]["papers"], [{"id": "md-test-0001", "title": "Graph methods"}])
        with self.assertRaises(ValueError):
            agent.prepare_actions([{"op": "delete", "paper": "md-test-0001"}], papers, folders, strict=True)

    def test_a_confirmed_plan_makes_the_changes(self):
        result = agent.apply([
            {"op": "new_folder", "name": "Graphs", "papers": ["md-test-0001", "md-test-0002"]},
            {"op": "rename_paper", "paper": "md-test-0002", "name": "Evidence, renamed"},
        ])
        folder = next(f for f in result["folders"]["folders"] if f["name"] == "Graphs")
        self.assertEqual(result["folders"]["of"]["md-test-0001"], folder["id"])
        self.assertEqual(result["folders"]["of"]["md-test-0002"], folder["id"])
        self.assertEqual(library.name_of("md-test-0002"), "Evidence, renamed")
        self.assertEqual(result["actions"][0]["papers"][1]["title"], "Graph evidence")


if __name__ == "__main__":
    unittest.main()
