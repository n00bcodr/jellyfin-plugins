#!/usr/bin/env python3
"""python3 -m unittest test_tooling  (no network)"""
import copy, json, os, unittest
from jfversion import V, require_four, strip_banner, with_banner
import build_unified_manifest as B
import validate_manifest as VM

HERE = os.path.dirname(os.path.abspath(__file__))

def working_manifest():
    """manifest.unified.json beside the tests (proposal layout) or ../manifest.json (tools/ layout in jellyfin-plugins)."""
    for cand in (os.path.join(HERE, "manifest.unified.json"), os.path.join(HERE, "..", "manifest.json")):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError("no manifest.unified.json beside the tests and no ../manifest.json")

def fixture(name):
    with open(os.path.join(HERE, "fixtures", name + ".manifest.json"), encoding="utf-8") as f:
        return json.load(f)

class VersionTests(unittest.TestCase):
    def test_system_version_ordering(self):
        self.assertLess(V("10.11"), V("10.11.0"))
        self.assertLess(V("10.11.0"), V("10.11.0.0"))
        self.assertLess(V("10.11.11.0"), V("12.0.0.0"))
        self.assertEqual(V("12.0.0.0"), V("12.0.0.0"))
    def test_rejects(self):
        for bad in ("12", "1.2.3.4.5", "", "12.0.0.0-rc1", "12.0.0.0\n", "١.2.3.4", "2147483648.0.0.0"):
            with self.assertRaises(ValueError, msg=bad):
                V(bad)
    def test_require_four(self):
        self.assertEqual(require_four("12.6.0.0", "tag"), "12.6.0.0")
        for bad in ("12.6.0", "12.6.0.0.0", "2147483648.0.0.0"):
            with self.assertRaises(SystemExit):
                require_four(bad, "tag")

class BannerTests(unittest.TestCase):
    head = "**Build for Jellyfin 12.**"
    def test_idempotent(self):
        once = with_banner(self.head, "- fix a\n- fix b")
        self.assertEqual(with_banner(self.head, once), once)
    def test_stacked_collapse(self):
        stacked = "\n\n".join([self.head, self.head, "**Build for Jellyfin 10.11 only. Not for Jellyfin 12.**", "- item"])
        out = with_banner(self.head, stacked)
        self.assertEqual(out.count("**Build for"), 1)
        self.assertTrue(out.endswith("- item"))
    def test_unrelated_bold_survives(self):
        self.assertTrue(strip_banner("**Build for ARM now available**\n- x").startswith("**Build for ARM"))
    def test_empty_body(self):
        self.assertEqual(with_banner(self.head, ""), self.head)
        self.assertEqual(with_banner(self.head, None), self.head)

class MergeTests(unittest.TestCase):
    def setUp(self):
        self.srcs = [(l, fixture(l)) for l in ("12", "10.11", "legacy", "10.10")]
        self.addCleanup(setattr, B, "md5_of", B.md5_of)      # every test below stubs the download
    def test_conflict_resolved_by_asset(self):
        # 10.3.0.0 @ 10.10.7.0: legacy checksum is the one that matches the real asset
        B.md5_of = lambda url: "B73BC27BF91161993B1F930232CD43FD"      # stub the download
        out = B.merge(copy.deepcopy(self.srcs))
        je = next(p for p in out if p["guid"] == "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b")
        row = next(v for v in je["versions"] if v["version"] == "10.3.0.0" and v["targetAbi"] == "10.10.7.0")
        self.assertEqual(row["checksum"], "B73BC27BF91161993B1F930232CD43FD")
    def test_every_input_row_once_and_ordered(self):
        B.md5_of = lambda url: "B73BC27BF91161993B1F930232CD43FD"
        out = B.merge(copy.deepcopy(self.srcs), annotate=False)
        want = {(p["guid"], v["version"], v["targetAbi"]) for _, m in self.srcs for p in m for v in p["versions"]}
        got = [(p["guid"], v["version"], v["targetAbi"]) for p in out for v in p["versions"]]
        self.assertEqual(set(got), want)
        self.assertEqual(len(got), len(set(got)))
        B.check(out)   # would sys.exit on a violation
    def test_reingest_is_stable(self):
        B.md5_of = lambda url: "B73BC27BF91161993B1F930232CD43FD"
        first = B.merge(copy.deepcopy(self.srcs))
        again = B.merge([(l, copy.deepcopy(first)) for l in ("12", "10.11", "legacy", "10.10")])
        self.assertEqual(first, again)

class FixtureProvenanceTests(unittest.TestCase):
    def test_fixtures_unmodified(self):
        import hashlib
        with open(os.path.join(HERE, "fixtures", "SHA256SUMS"), encoding="utf-8") as f:
            for line in f:
                digest, name = line.split()
                with open(os.path.join(HERE, "fixtures", name), "rb") as g:
                    self.assertEqual(hashlib.sha256(g.read()).hexdigest(), digest, name)

class TripwireTests(unittest.TestCase):
    def test_jprm_collapse_is_caught(self):
        with open(working_manifest(), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(VM.tripwire(m), [])
        collapsed = copy.deepcopy(m)
        je = next(p for p in collapsed if p["guid"] == "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b")
        je["versions"] = [v for v in je["versions"] if not (v["version"] == "12.5.0.0" and v["targetAbi"] == "12.0.0.0")]
        self.assertTrue(any("12.5.0.0: no 12.0.0.0 row" in b for b in VM.tripwire(collapsed)))
        collapsed2 = copy.deepcopy(m)
        je = next(p for p in collapsed2 if p["guid"] == "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b")
        je["versions"] = [v for v in je["versions"] if not (v["version"] == "12.5.0.0" and v["targetAbi"] == "10.11.0.0")]
        self.assertTrue(any("12.5.0.0: no 10.11.0.0 row" in b for b in VM.tripwire(collapsed2)))
        swapped = copy.deepcopy(m)
        je = next(p for p in swapped if p["guid"] == "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b")
        je["versions"][0], je["versions"][1] = je["versions"][1], je["versions"][0]
        self.assertTrue(any("listed AFTER" in b for b in VM.tripwire(swapped)))

if __name__ == "__main__":
    unittest.main()
