"""The skill is self-contained and honest, and its docs agree with the script.
Stdlib unittest only.

  1. SKILL.md is a valid, stand-alone Agent Skill: the folder name matches the
     skill name, the description fits, every file it points at exists, and it
     says nothing about the plugin it was extracted from (commands, brand
     profiles, plugin variables, sibling skills, agents).
  2. The docs are checked against the code, not against each other: the crawler
     table matches AI_CRAWLERS row for row (vendor, role, must-be-allowed or
     policy), every check id, required attribute, conversational attribute,
     flag and exit code the script has is documented, and the documented
     defaults are the real defaults.
  3. The honesty rules are machine-checked: llms.txt is only ever mentioned in
     a negative sentence, no model ids or prices appear in the prose, and no
     client or organisation name from the maintainer's other work ends up in
     any file.
"""
from __future__ import annotations

import ast
import json
import re
import unittest

from _support import (README, ROOT, SCRIPT, SKILL, SKILL_MD, crawler_rows, frontmatter,
                      load_module, read)

ara = load_module("agent_readiness_audit", SCRIPT)

# What the plugin this skill was extracted from calls things. None of it exists here.
PLUGIN_ONLY = [
    r"/digital-marketing-pro:", r"CLAUDE_PLUGIN_ROOT", r"CLAUDE_PLUGIN_DATA",
    r"claude-marketing", r"_active-brand", r"brand profile", r"brand-setup", r"profile\.json",
    r"seo-specialist", r"media-buyer", r"tech-seo-audit", r"entity-audit", r"aeo-geo",
    r"geo-monitor", r"gsc-ai-performance", r"skills/paid-advertising", r"ads-in-ai-answers",
    r"Agents used", r"argument-hint",
]

ROLE_LABEL = {"search": "search", "user": "user fetch", "ads": "ads", "training": "training"}
DMP_URL = r"https://github\.com/indranilbanerjee/digital-marketing-pro(?![\w-])"


class TestSkillHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = read(SKILL_MD)
        cls.fm, cls.body = frontmatter(cls.raw)

    def test_frontmatter(self):
        self.assertEqual(self.fm["name"], "agent-readiness-audit")
        self.assertEqual(self.fm["name"], SKILL.name)  # must match the folder
        self.assertRegex(self.fm["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertEqual(self.fm["license"], "MIT")
        desc = self.fm["description"]
        self.assertTrue(desc.startswith('"') and desc.endswith('"'), "quote the description")
        desc = json.loads(desc)  # a double-quoted YAML scalar is valid JSON here
        self.assertTrue(0 < len(desc) <= 1024, len(desc))
        low = desc.lower()
        for needle in ("use when", "robots.txt", "json-ld", "native_commerce", "webmcp",
                       "agent_readiness_audit.py", "llms.txt"):
            self.assertIn(needle, low)

    def test_no_triggers_field_and_no_plugin_only_fields(self):
        self.assertNotIn("triggers", self.fm)
        self.assertNotIn("argument-hint", self.fm)
        self.assertEqual(set(self.fm), {"name", "description", "license", "compatibility",
                                        "metadata"})

    def test_every_file_skill_md_points_at_exists(self):
        refs = {r.rstrip(".,") for r in
                re.findall(r"(?<![\w/.-])((?:scripts|references)/[\w./-]+)", self.raw)}
        self.assertEqual(refs, {"scripts/agent_readiness_audit.py"})
        for ref in sorted(refs):
            with self.subTest(ref=ref):
                self.assertTrue((SKILL / ref).is_file(), ref)

    def test_script_path_is_relative_to_the_skill_folder(self):
        self.assertIn("<skill-dir>/scripts/agent_readiness_audit.py", self.body)
        self.assertNotRegex(self.body, r"[A-Za-z]:\\")
        self.assertNotIn("/Users/", self.body)

    def test_no_references_to_the_plugin_it_came_from(self):
        for pattern in PLUGIN_ONLY:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.raw, re.I),
                                  f"SKILL.md mentions plugin-only thing: {pattern}")
        self.assertIsNone(re.search(r"\bDMP\b(?!-agent-readiness-audit)", self.raw),
                          "the only DMP in SKILL.md is the User-Agent string")

    def test_exactly_one_link_back_to_the_suite(self):
        self.assertEqual(len(re.findall(DMP_URL, self.raw)), 1)

    def test_has_the_sections_a_single_agent_needs(self):
        for heading in ("## What it checks", "## What the primary sources say",
                        "## What you need", "## Running the audit", "## Method",
                        "## Self-check before you report", "## Output", "## Caveats",
                        "## What this is not"):
            self.assertIn(heading, self.body)

    def test_framing_sentence_comes_first(self):
        first = self.body.strip().split("\n\n")[1]  # after the H1
        flat = " ".join(first.split())
        self.assertIn("It does not predict rankings or citations", flat)
        self.assertIn("never recommends llms.txt for Google", flat)


class TestDocsAgreeWithTheScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL_MD)
        cls.readme = read(README)

    def test_crawler_table_matches_the_script_row_for_row(self):
        rows = crawler_rows(self.skill)
        self.assertEqual(set(rows), {b["token"] for b in ara.AI_CRAWLERS})
        self.assertEqual(len(rows), len(ara.AI_CRAWLERS))
        for bot in ara.AI_CRAWLERS:
            with self.subTest(token=bot["token"]):
                vendor, role_cell = rows[bot["token"]]
                self.assertEqual(vendor, bot["vendor"])
                self.assertTrue(role_cell.startswith(ROLE_LABEL[bot["role"]] + ":"), role_cell)
                if bot["role"] in ara.REQUIRED_ROLES:
                    self.assertIn("**must be allowed**", role_cell)
                else:
                    self.assertIn("**policy**", role_cell)

    def test_readme_names_every_crawler_token(self):
        for bot in ara.AI_CRAWLERS:
            with self.subTest(token=bot["token"]):
                self.assertIn(bot["token"], self.readme)
        self.assertEqual(len(ara.AI_CRAWLERS), 13)
        self.assertIn("Thirteen tokens", self.readme)

    def test_every_vendor_source_url_is_cited_in_the_skill_table(self):
        for bot in ara.AI_CRAWLERS:
            with self.subTest(token=bot["token"]):
                self.assertIn(bot["source"], self.skill)

    def test_every_check_id_is_documented_in_both_files(self):
        run = ara.run_audit(ara.build_parser().parse_args(["--robots", str(ROOT / "examples" / "robots.txt")]))
        for check in run["checks"]:
            with self.subTest(check=check["id"]):
                self.assertIn(check["id"], self.skill)
        # The README describes the same seven checks in plain words.
        for word in ("robots.txt", "Structured data", "No-JavaScript render", "Accessibility basics",
                     "Merchant Center feed", "Agentic-commerce feed", "WebMCP"):
            self.assertIn(word, self.readme)

    def test_required_and_conversational_attributes_are_documented(self):
        for attr in ara.MC_REQUIRED + ara.CONVERSATIONAL:
            with self.subTest(attribute=attr):
                self.assertIn(f"`{attr}`", self.skill)
        for attr in ara.CONVERSATIONAL:
            self.assertIn(f"`{attr}`", self.readme)
        for value in sorted(ara.MC_AVAILABILITY):
            self.assertIn(f"`{value}`", self.skill)

    def test_every_flag_is_documented(self):
        parser = ara.build_parser()
        flags = {s for a in parser._actions for s in a.option_strings if s.startswith("--") and s != "--help"}
        self.assertGreaterEqual(len(flags), 12)
        for flag in sorted(flags):
            with self.subTest(flag=flag):
                self.assertIn(flag, self.skill)

    def test_documented_defaults_are_the_real_defaults(self):
        args = ara.build_parser().parse_args(["--robots", "x"])
        self.assertEqual(args.min_text, 250)
        self.assertIn("default 250 characters", self.skill)
        self.assertEqual(args.training_policy, "either")
        self.assertIn("The default, `either`", self.skill)
        self.assertEqual(args.format, "json")
        self.assertFalse(args.fetch)

    def test_exit_codes_are_documented(self):
        for code in ("`0`", "`1`", "`2`"):
            self.assertIn(code, self.skill)
            self.assertIn(code, self.readme)

    def test_the_sources_date_is_the_scripts_date(self):
        self.assertIn(f"(checked {ara.CHECKED})", self.skill)
        self.assertIn(f"Checked {ara.CHECKED}", self.readme)
        self.assertIn(ara.CHECKED, ara.LLMS_TXT_NOTE)

    def test_every_source_url_in_the_script_is_listed_in_the_readme(self):
        doc = ast.get_docstring(ast.parse(read(SCRIPT)))
        urls = {u.rstrip(".,)") for u in re.findall(r"https://\S+", doc) if "example.com" not in u}
        self.assertGreaterEqual(len(urls), 14)
        sources = self.readme.split("## Sources")[1].split("## Part of")[0]
        for url in sorted(urls):
            with self.subTest(url=url):
                self.assertIn(url, sources)


class TestHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {}
        for path in ROOT.rglob("*"):
            parts = set(path.relative_to(ROOT).parts)
            if not path.is_file() or parts & {".git", "__pycache__", ".pytest_cache"}:
                continue
            try:
                cls.files[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
        cls.prose = {name: text for name, text in cls.files.items()
                     if name in ("README.md", "skills/agent-readiness-audit/SKILL.md",
                                 "skills/agent-readiness-audit/scripts/agent_readiness_audit.py")}

    def test_llms_txt_is_only_ever_mentioned_negatively(self):
        negations = ("never", "not", "n't", "mythbusting")
        seen = 0
        for name, text in self.prose.items():
            lines = text.splitlines()
            for n, line in enumerate(lines):
                if "llms" in line.lower():
                    seen += 1
                    # a hard-wrapped sentence may carry its negation on a neighbouring line
                    window = " ".join(lines[max(0, n - 1):n + 2]).lower()
                    with self.subTest(file=name, line=n + 1):
                        self.assertTrue(any(w in window for w in negations), line)
        self.assertGreaterEqual(seen, 8)  # the guard is looking at real mentions

    def test_framing_sentence_in_skill_md_and_readme(self):
        for label, text in (("SKILL.md", read(SKILL_MD)), ("README.md", read(README))):
            flat = " ".join(text.split())
            with self.subTest(file=label):
                self.assertRegex(flat, r"never recommends? llms\.txt for Google")
                self.assertRegex(flat, r"Google Search itself doesn't use them")
                self.assertRegex(flat, r"Mythbusting generative AI search")

    def test_no_model_ids_and_no_prices_in_the_prose(self):
        for name, text in self.prose.items():
            with self.subTest(file=name):
                self.assertIsNone(re.search(
                    r"\b(?:gpt|claude|gemini|llama|grok|mistral|opus|sonnet|haiku)[-\s]?\d", text, re.I))
                self.assertIsNone(re.search(r"[$€£]\s?\d", text))
                self.assertIsNone(re.search(r"\bper (?:month|seat|1k|million)\b", text, re.I))

    def test_no_other_organisation_or_local_paths_anywhere(self):
        banned = ["tech" + "shu"]  # built from parts so this file does not contain the name
        for name, text in self.files.items():
            with self.subTest(file=name):
                low = text.lower()
                for b in banned:
                    self.assertNotIn(b, low)
                self.assertIsNone(re.search(r"[A-Za-z]:\\Users\\", text))
                self.assertNotIn("@gmail" + ".com", low)  # no personal email address

    def test_script_is_stdlib_only_and_does_not_import_the_suite(self):
        imported = set()
        for node in ast.walk(ast.parse(read(SCRIPT))):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "argparse", "csv", "html", "io", "ipaddress", "json",
                                        "pathlib", "re", "socket", "sys", "urllib", "xml"})


class TestRepoFiles(unittest.TestCase):
    def test_license_and_gitignore(self):
        lic = read(ROOT / "LICENSE")
        self.assertIn("MIT License", lic)
        self.assertIn("Copyright (c) 2026 Indranil Banerjee", lic)
        gi = read(ROOT / ".gitignore")
        self.assertIn("__pycache__/", gi)
        self.assertNotRegex(gi, r"(?m)^\*\.tsv$")  # examples/products.tsv must stay tracked

    def test_layout(self):
        for rel in ("skills/agent-readiness-audit/SKILL.md",
                    "skills/agent-readiness-audit/scripts/agent_readiness_audit.py",
                    "examples/robots.txt", "examples/spa-shell.html", "examples/products.tsv",
                    "tests/test_audit.py", "tests/test_skill.py", "tests/test_readme.py",
                    "tests/test_parity.py", "README.md", "LICENSE", ".gitignore", ".gitattributes"):
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), rel)

    def test_one_line_ending_rule(self):
        self.assertIn("eol=lf", read(ROOT / ".gitattributes"))

    def test_there_is_no_references_folder_the_skill_does_not_need(self):
        # SKILL.md is self-contained; an empty or unreferenced references/ would mislead.
        self.assertFalse((SKILL / "references").exists())


if __name__ == "__main__":
    unittest.main()
