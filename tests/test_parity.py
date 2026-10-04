"""Parity with Digital Marketing Pro. Stdlib unittest only.

The script in this repository is a copy of Digital Marketing Pro's
`scripts/agent-readiness-audit.py`. A copy can drift, so when a Digital
Marketing Pro checkout is alongside (`../../digital-marketing-pro` relative to
this repository; override with $DMP_DIR) these tests prove the two are the same
program, three ways:

  1. SAME CODE. The two files have an identical syntax tree once the module
     docstring is set aside, and they are byte-identical outside it (shebang
     line and everything after the docstring). The docstrings differ in exactly
     one way, justified below: the file name, because the Agent Skills standard
     makes the script live at `scripts/agent_readiness_audit.py` (an
     underscore) while the plugin's is `agent-readiness-audit.py`. Three
     docstring lines name the file (the title and the two usage examples).
  2. SAME OUTPUT. The two scripts are run as subprocesses on the same files
     with the same arguments, over a corpus of well over 100 invocations (every
     fixture, every flag, text and JSON, every exit-code path, --help). Exit
     code and stdout must be identical bytes. Where argparse prints the program
     name (usage text), the name is the only difference allowed.
  3. SAME FETCH BEHAVIOUR. `run_audit` is run in-process on both modules with
     the same fake server (200, 404, 503, a network error, a non-200 page).

Each of the tests below skips when the sibling is absent, so a stand-alone
clone still passes. They only ever READ the sibling: bytecode writing is
disabled and nothing is written there. TestSkipPath proves the skip path by
running this module in a subprocess with $DMP_DIR pointing at an empty folder.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import _fixtures as fx
from _support import ROOT, SCRIPT, SKILL_MD, crawler_rows, load_module, norm_eol, read, run_script

DMP_ROOT = Path(os.environ.get("DMP_DIR") or (ROOT / ".." / ".." / "digital-marketing-pro")).resolve()
DMP_SCRIPT = DMP_ROOT / "scripts" / "agent-readiness-audit.py"
DMP_SKILL_MD = DMP_ROOT / "skills" / "agent-readiness-audit" / "SKILL.md"
HAVE_DMP = DMP_SCRIPT.is_file()
SKIP_REASON = "Digital Marketing Pro not found alongside this repo (../../digital-marketing-pro, or set DMP_DIR)"

HERO_NAME, DMP_NAME = "agent_readiness_audit.py", "agent-readiness-audit.py"
NESTED = "ARA_PARITY_SKIPCHECK"  # set by TestSkipPath so its child run does not recurse


def _split(text: str):
    """(before_docstring, docstring_source, after_docstring, tree) for a script, LF-normalised."""
    text = norm_eol(text.encode("utf-8")).decode("utf-8")
    tree = ast.parse(text)
    first = tree.body[0]
    assert (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)), "script must open with a module docstring"
    lines = text.split("\n")
    return ("\n".join(lines[:first.lineno - 1]),
            "\n".join(lines[first.lineno - 1:first.end_lineno]),
            "\n".join(lines[first.end_lineno:]),
            tree)


def _dump_without_module_docstring(tree) -> str:
    return ast.dump(ast.Module(body=tree.body[1:], type_ignores=[]))


@unittest.skipUnless(HAVE_DMP, SKIP_REASON)
class TestSameCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hero = _split(read(SCRIPT))
        cls.dmp = _split(read(DMP_SCRIPT))

    def test_syntax_trees_are_identical_modulo_the_module_docstring(self):
        self.assertEqual(_dump_without_module_docstring(self.hero[3]),
                         _dump_without_module_docstring(self.dmp[3]))

    def test_byte_identical_outside_the_module_docstring(self):
        self.assertEqual(self.hero[0], self.dmp[0], "shebang / preamble")
        self.assertEqual(self.hero[2], self.dmp[2], "everything after the docstring")

    def test_docstrings_differ_only_by_the_file_name(self):
        hero_doc, dmp_doc = self.hero[1], self.dmp[1]
        self.assertEqual(hero_doc.count(HERO_NAME), 3)
        self.assertEqual(dmp_doc.count(DMP_NAME), 3)
        self.assertEqual(hero_doc.replace(HERO_NAME, DMP_NAME), dmp_doc)

    def test_the_file_name_appears_nowhere_else(self):
        # The only text that would change if the name were wrong is the docstring.
        self.assertNotIn(HERO_NAME, self.hero[2])
        self.assertNotIn(DMP_NAME, self.hero[2])

    def test_whole_file_equal_after_undoing_the_documented_rename(self):
        hero = read(SCRIPT).replace("\r\n", "\n").replace(HERO_NAME, DMP_NAME)
        self.assertEqual(hero, read(DMP_SCRIPT).replace("\r\n", "\n"))


def _corpus(tmp: Path):
    """Write the fixtures into `tmp` and return [(label, args)] to run in `tmp`."""
    files = {
        "open.txt": fx.ROBOTS_OPEN, "blocks.txt": fx.ROBOTS_BLOCKS_SEARCH,
        "training.txt": fx.ROBOTS_TRAINING_BLOCKED, "empty.txt": fx.ROBOTS_EMPTY,
        "good.html": fx.HTML_GOOD, "shell.html": fx.HTML_SPA_SHELL,
        "badld.html": fx.HTML_BAD_JSONLD, "nooffer.html": fx.HTML_PRODUCT_NO_OFFER,
        "a11y.html": fx.HTML_A11Y_ISSUES, "nolandmark.html": fx.HTML_NO_LANDMARKS,
        "f.tsv": fx.FEED_TSV, "clean.tsv": fx.FEED_TSV_CLEAN, "badprice.tsv": fx.FEED_TSV_BAD_PRICE,
        "f.csv": fx.FEED_CSV_CLEAN, "f.xml": fx.FEED_XML, "broken.xml": fx.FEED_XML_BROKEN,
        "ok.jsonl": fx.ACP_JSONL_OK, "missing.jsonl": fx.ACP_JSONL_MISSING,
        "badline.jsonl": fx.ACP_JSONL_BAD_LINE, "zero.txt": "",
    }
    for name, text in files.items():
        (tmp / name).write_bytes(text.encode("utf-8"))
    (tmp / "latin1.txt").write_bytes(b"User-agent: *\n\xff\xfe\n")
    # the shipped examples, so the README's run is part of the corpus
    for p in (ROOT / "examples").iterdir():
        (tmp / p.name).write_bytes(p.read_bytes())

    runs = []
    robots = ["open.txt", "blocks.txt", "training.txt", "empty.txt", "robots.txt"]
    for r in robots:
        for policy in ("either", "allow", "block"):
            for paths in ([], ["/cart/"], ["/products/", "/cart/"]):
                args = ["--robots", r, "--training-policy", policy]
                for p in paths:
                    args += ["--path", p]
                runs.append((f"robots {r} {policy} {paths}", args))
        runs.append((f"robots {r} text", ["--robots", r, "--format", "text"]))
    htmls = ["good.html", "shell.html", "badld.html", "nooffer.html", "a11y.html",
             "nolandmark.html", "spa-shell.html"]
    for h in htmls:
        for expect in ([], ["Acme Anvil"], ["Acme Anvil", "Titanium Hammer"]):
            for webmcp in (False, True):
                args = ["--html", h]
                for e in expect:
                    args += ["--expect", e]
                if webmcp:
                    args.append("--webmcp")
                runs.append((f"html {h} {expect} webmcp={webmcp}", args))
        runs.append((f"html {h} min-text 5", ["--html", h, "--min-text", "5"]))
        runs.append((f"html {h} text", ["--html", h, "--format", "text"]))
    runs.append(("two pages", ["--html", "good.html", "--html", "shell.html", "--webmcp"]))
    for f in ("f.tsv", "clean.tsv", "badprice.tsv", "f.csv", "f.xml", "products.tsv"):
        runs.append((f"feed {f}", ["--feed", f]))
        runs.append((f"feed {f} text", ["--feed", f, "--format", "text"]))
    for a in ("ok.jsonl", "missing.jsonl", "f.csv", "f.tsv"):
        runs.append((f"acp {a}", ["--acp-feed", a]))
    runs.append(("everything", ["--robots", "blocks.txt", "--path", "/p/", "--html", "good.html",
                               "--html", "shell.html", "--expect", "Acme Anvil", "--feed", "f.tsv",
                               "--acp-feed", "ok.jsonl", "--webmcp", "--training-policy", "block"]))
    runs.append(("the README run", ["--robots", "robots.txt", "--html", "spa-shell.html",
                                    "--expect", "Acme Anvil", "--feed", "products.tsv", "--webmcp",
                                    "--format", "text"]))
    runs.append(("site label only", ["--robots", "open.txt", "--site", "https://acme.example"]))
    # exit-code-2 paths and argparse behaviour
    runs += [
        ("no args", []),
        ("--help", ["--help"]),
        ("missing file", ["--robots", "does-not-exist.txt"]),
        ("not utf-8", ["--robots", "latin1.txt"]),
        ("bad policy", ["--training-policy", "sometimes"]),
        ("bad format", ["--robots", "open.txt", "--format", "xml"]),
        ("unknown flag", ["--robots", "open.txt", "--nope"]),
        ("fetch without site", ["--fetch"]),
        ("fetch non-http", ["--fetch", "--site", "ftp://acme.example"]),
        ("empty feed", ["--feed", "zero.txt"]),
        ("broken xml", ["--feed", "broken.xml"]),
        ("bad jsonl", ["--acp-feed", "badline.jsonl"]),
        ("feed missing", ["--feed", "nope.tsv"]),
    ]
    return runs


def _normalise(s: str) -> str:
    return s.replace(HERO_NAME, DMP_NAME)


@unittest.skipUnless(HAVE_DMP, SKIP_REASON)
class TestSameOutput(unittest.TestCase):
    def test_outputs_are_identical_across_the_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            runs = _corpus(tmp)
            self.assertGreaterEqual(len(runs), 100)

            def pair(item):
                label, args = item
                return label, args, run_script(*args, script=SCRIPT, cwd=tmp), \
                    run_script(*args, script=DMP_SCRIPT, cwd=tmp)

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(pair, runs))

        codes = set()
        for label, args, (hc, hout, herr), (dc, dout, derr) in results:
            codes.add(dc)
            with self.subTest(run=label):
                self.assertEqual(hc, dc, "exit code")
                if hout == dout and herr == derr:
                    continue
                # Only argparse's usage text (--help, bad flags) may differ, and only by
                # the program name it prints.
                self.assertIn("usage:", hout + herr)
                self.assertEqual(_normalise(hout), dout)
                self.assertEqual(_normalise(herr), derr)
        self.assertEqual(codes, {0, 1, 2}, "the corpus must exercise every exit code")

    def test_the_corpus_is_not_vacuous(self):
        # A couple of spot checks that the runs produced real, different reports.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _corpus(tmp)
            ready = run_script("--robots", "open.txt", "--html", "good.html", script=DMP_SCRIPT, cwd=tmp)
            broken = run_script("--html", "shell.html", script=DMP_SCRIPT, cwd=tmp)
        self.assertIn('"verdict": "ready"', ready[1])
        self.assertIn('"verdict": "not_ready"', broken[1])


class _FakeResp:
    def __init__(self, body: str, status: int = 200):
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = mock.Mock()
        self.headers.get_content_charset.return_value = "utf-8"

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@unittest.skipUnless(HAVE_DMP, SKIP_REASON)
class TestSameFetchBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hero = load_module("hero_ara_parity", SCRIPT, register=False)
        cls.dmp = load_module("dmp_ara_parity", DMP_SCRIPT, register=False)

    def _both(self, handler, argv):
        reports = []
        for mod in (self.hero, self.dmp):
            with mock.patch.object(mod.urllib.request, "urlopen", side_effect=handler(mod)):
                try:
                    reports.append(mod.run_audit(mod.build_parser().parse_args(argv)))
                except mod.BadInput as e:
                    reports.append(("BadInput", str(e)))
        return reports

    def test_scenarios(self):
        site = ["--site", "https://acme.example", "--fetch"]
        pages = ["--page", "https://acme.example/p/anvil"]

        def serving(robots, page):
            def make(mod):
                def fake(req, timeout=15):
                    url = req.full_url
                    if url.endswith("/robots.txt"):
                        if isinstance(robots, int):
                            raise mod.urllib.error.HTTPError(url, robots, "x", {}, None)
                        return _FakeResp(robots)
                    if isinstance(page, int):
                        raise mod.urllib.error.HTTPError(url, page, "x", {}, None)
                    if page is None:
                        raise mod.urllib.error.URLError("no route to host")
                    return _FakeResp(page)
                return fake
            return make

        scenarios = {
            "200 robots and page": (serving(fx.ROBOTS_BLOCKS_SEARCH, fx.HTML_GOOD), site + pages),
            "robots 404 is allow-all": (serving(404, fx.HTML_GOOD), site),
            "robots 410 is allow-all": (serving(410, fx.HTML_SPA_SHELL), site + pages),
            "robots 503 means disallow-all": (serving(503, fx.HTML_GOOD), site),
            "page network error": (serving(fx.ROBOTS_OPEN, None), site),
            "page 500": (serving(fx.ROBOTS_OPEN, 500), site),
            "everything fails": (serving(503, 503), site),
            "bad site url": (serving(fx.ROBOTS_OPEN, fx.HTML_GOOD), ["--site", "ftp://acme.example", "--fetch"]),
        }
        for name, (handler, argv) in scenarios.items():
            with self.subTest(scenario=name):
                hero, dmp = self._both(handler, argv)
                self.assertEqual(hero, dmp)
        # the corpus saw both a report and an error, so the comparison is not vacuous
        kinds = {type(self._both(*scenarios[n])[0]).__name__ for n in
                 ("200 robots and page", "bad site url")}
        self.assertEqual(kinds, {"dict", "tuple"})

    def test_user_agent_and_constants(self):
        for name in ("USER_AGENT", "TOOL_VERSION", "CHECKED", "AI_CRAWLERS", "REQUIRED_ROLES",
                     "MC_REQUIRED", "MC_AVAILABILITY", "CONVERSATIONAL", "ACP_JSONL_REQUIRED",
                     "ACP_CSV_REQUIRED", "LLMS_TXT_NOTE", "STRUCTURED_DATA_NOTE"):
            with self.subTest(constant=name):
                self.assertEqual(getattr(self.hero, name), getattr(self.dmp, name))


@unittest.skipUnless(HAVE_DMP, SKIP_REASON)
class TestSkillDocsStayInStep(unittest.TestCase):
    """SKILL.md is rewritten for stand-alone use, not copied, so it cannot be
    byte-compared. What must not drift is the catalogue of facts both versions
    state about the script: the same crawler tokens, with the same vendors."""

    def test_crawler_tables_list_the_same_tokens_and_vendors(self):
        hero = crawler_rows(read(SKILL_MD))
        dmp = crawler_rows(read(DMP_SKILL_MD))
        self.assertGreaterEqual(len(dmp), 10)
        self.assertEqual({t: v for t, (v, _) in hero.items()}, {t: v for t, (v, _) in dmp.items()})

    def test_both_state_the_same_check_date(self):
        ara = load_module("hero_ara_date", SCRIPT, register=False)
        for path in (SKILL_MD, DMP_SKILL_MD):
            with self.subTest(file=str(path.parent.name)):
                self.assertIn(ara.CHECKED, read(path))


# ---------------------------------------------------------------------------
# Always runs: proves the skip path, so a stand-alone clone passes
# ---------------------------------------------------------------------------

@unittest.skipIf(os.environ.get(NESTED), "child run of TestSkipPath")
class TestSkipPath(unittest.TestCase):
    def test_parity_tests_skip_cleanly_when_the_sibling_is_absent(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, DMP_DIR=str(Path(td) / "no-such-checkout"), PYTHONDONTWRITEBYTECODE="1",
                       **{NESTED: "1"})
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(Path(__file__).parent),
                 "-p", "test_parity.py", "-v"],
                capture_output=True, env=env, cwd=ROOT, timeout=300)
        err = proc.stderr.decode("utf-8")
        self.assertEqual(proc.returncode, 0, err)
        skipped = re.search(r"OK \(skipped=(\d+)\)", err)
        self.assertIsNotNone(skipped, err)
        self.assertGreaterEqual(int(skipped.group(1)), 10)  # every parity test was skipped
        self.assertIn("Digital Marketing Pro not found alongside", err)
        self.assertNotIn("FAIL", err)
        self.assertNotIn("ERROR", err)

    def test_the_sibling_lookup_honours_the_env_var(self):
        # HAVE_DMP is computed from DMP_ROOT, and DMP_ROOT from $DMP_DIR.
        self.assertEqual(HAVE_DMP, DMP_SCRIPT.is_file())
        if os.environ.get("DMP_DIR"):
            self.assertEqual(DMP_ROOT, Path(os.environ["DMP_DIR"]).resolve())


if __name__ == "__main__":
    unittest.main()
