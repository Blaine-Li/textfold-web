"""The browser's prewritten example is usable offline and never overwrites a reader's work."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from textfold import fold, llm, local, notes, server, store, web_demo


class WebDemo(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        data = mock.patch.object(store, "DATA", Path(temporary.name))
        data.start()
        self.addCleanup(data.stop)
        model = mock.patch.object(llm, "call", side_effect=AssertionError("The reading sample must not call a model"))
        self.model = model.start()
        self.addCleanup(model.stop)
        network = mock.patch("urllib.request.urlopen", side_effect=AssertionError("The reading sample must work offline"))
        self.network = network.start()
        self.addCleanup(network.stop)

    def test_sample_has_three_sections_six_paragraphs_and_five_readable_levels(self):
        pid = web_demo.ensure_sample()
        self.assertEqual(pid, web_demo.DEMO_ID)
        doc = fold.document(pid)
        self.assertEqual(doc["lang"], "zh")
        self.assertEqual(doc["levels"], ["topic", "takeaway", "key", "brief", "full"])
        self.assertEqual(len(doc["sections"]), 3)
        self.assertEqual(sum(len(section["units"]) for section in doc["sections"]), 6)
        self.assertEqual(doc["provenance"]["model"], "prewritten-web-sample")
        for section, expected in zip(doc["sections"], web_demo.SECTIONS):
            self.assertEqual(section["title"], expected[0])
            self.assertTrue(section["topic"])
            self.assertEqual(len(section["units"]), 2)
            for unit, paragraph in zip(section["units"], expected[2]):
                for level in doc["levels"]:
                    self.assertTrue(unit[level], (unit["id"], level))
                self.assertEqual(unit["takeaway"], paragraph[1])
                self.assertIn(paragraph[2], unit["key"])
                self.assertIn(unit["brief"][0], unit["full"])
        for level in doc["levels"]:
            self.assertIn("TextFold 网页阅读指南", fold.markdown(doc, level))
        self.model.assert_not_called()
        self.network.assert_not_called()

    def test_repeat_launch_preserves_edited_source_notes_and_file_contents(self):
        pid = web_demo.ensure_sample()
        unit = next(iter(store.assemble(pid)["units"]))
        notes.put(pid, {"id": "n-example-note", "text": "我的阅读批注", "anchor": {"unit": unit, "lang": "zh"}})
        revised = web_demo.TEXT + "\n\n## 我的补充\n\n这是阅读之后写下的文字。\n"
        local.replace_text(pid, revised)
        directory = store.pdir(pid)
        before = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        self.assertEqual(web_demo.ensure_sample(), pid)
        after = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(local.text_of(pid), revised)
        self.assertEqual(notes.read(pid)["notes"][0]["text"], "我的阅读批注")
        self.model.assert_not_called()
        self.network.assert_not_called()

    def landing_boot(self):
        payload = {"selectedName": "", "askName": "", "bridge": {}, "capabilities": {"web": True}}
        jobs = mock.Mock()
        jobs.list.return_value = []
        with mock.patch.object(server.agents, "wait_scanned"), \
             mock.patch.object(server, "models_payload", return_value=payload), \
             mock.patch.object(server, "listed", return_value=[]), \
             mock.patch.object(server.library, "folders", return_value=[]):
            page = server.landing_page(jobs)
        boot = re.search(r'<script id="boot" type="application/json">(.*?)</script>', page, re.S)
        self.assertIsNotNone(boot)
        return json.loads(boot.group(1))

    def test_environment_only_web_mode_has_no_broken_sample_link(self):
        self.assertIsNone(self.landing_boot()["demo"])
        self.assertFalse(store.has(web_demo.DEMO_ID))
        web_demo.ensure_sample()
        self.assertEqual(self.landing_boot()["demo"], {"id": web_demo.DEMO_ID})


if __name__ == "__main__":
    unittest.main()
