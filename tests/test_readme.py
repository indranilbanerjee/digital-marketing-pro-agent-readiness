"""The README is accurate, and its example is a real run. Stdlib unittest only.

The "A real run" section shows three fixture files, one command, its exit code,
its complete text output, and trimmed excerpts of the JSON the same command
prints. These tests re-run that command from the repository root and compare:

  * each fixture block equals the file in examples/ byte for byte (tabs included);
  * the command block is parsed and executed as written (so a flag typo in the
    README fails here), and the exit code it states is the exit code it returns;
  * the text output block equals the real stdout exactly;
  * every excerpt of the JSON is a contiguous slice of the real JSON output, in
    order, with the cuts marked by a line holding only an ellipsis. Edit a
    number inside an excerpt and this fails.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import unittest

from _support import EXAMPLES, README, ROOT, fenced_after, read

CMD_LABEL = "Run from the repository root:"
TEXT_LABEL = "The output (a real run, unedited):"
JSON_LABEL_PREFIX = "The same run without `--format text` prints JSON"


def run_readme_command(drop_text_format: bool):
    block = fenced_after(read(README), CMD_LABEL)
    argv = shlex.split(re.sub(r"\\\n\s*", " ", block))
    assert argv[0] == "python", argv[0]
    argv[0] = sys.executable
    if drop_text_format:
        i = argv.index("--format")
        del argv[i:i + 2]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([argv[0], "-B", *argv[1:]], cwd=ROOT, capture_output=True, env=env, timeout=120)
    return proc.returncode, proc.stdout.decode("utf-8").replace("\r\n", "\n"), proc.stderr.decode("utf-8")


class TestReadmeIsAccurate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = read(README)

    def test_install_and_layout(self):
        self.assertIn("npx skills add indranilbanerjee/digital-marketing-pro-agent-readiness", self.readme)
        self.assertIn("git clone https://github.com/indranilbanerjee/digital-marketing-pro-agent-readiness",
                      self.readme)
        self.assertIn("skills/agent-readiness-audit", self.readme)
        self.assertIn("~/.claude/skills/agent-readiness-audit", self.readme)
        self.assertGreaterEqual(len(self.readme.split()), 400)

    def test_exactly_one_link_back_to_the_suite_in_its_own_section(self):
        links = re.findall(r"https://github\.com/indranilbanerjee/digital-marketing-pro(?![\w-])", self.readme)
        self.assertEqual(len(links), 1)
        section = self.readme.split("## Part of Digital Marketing Pro")[1]
        self.assertIn(links[0], section)

    def test_what_it_never_does_names_the_google_guide(self):
        section = self.readme.split("## What it never does")[1].split("## Install")[0]
        self.assertIn("llms.txt for Google", section)
        self.assertIn("https://developers.google.com/search/docs/fundamentals/ai-optimization-guide", section)

    def test_every_documented_example_command_uses_real_flags(self):
        from _support import SCRIPT, load_module
        ara = load_module("agent_readiness_audit", SCRIPT)
        flags = {s for a in ara.build_parser()._actions for s in a.option_strings}
        used = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", "\n".join(
            re.findall(r"```bash\n(.*?)```", self.readme, re.S))))
        self.assertTrue(used)
        self.assertLessEqual(used, flags)


class TestTheRealRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = read(README)
        cls.code, cls.text_out, cls.text_err = run_readme_command(drop_text_format=False)
        cls.json_code, cls.json_out, _ = run_readme_command(drop_text_format=True)

    def test_fixture_blocks_are_the_example_files(self):
        for name in ("robots.txt", "spa-shell.html", "products.tsv"):
            with self.subTest(file=name):
                block = fenced_after(self.readme, f"**`examples/{name}`**")
                self.assertEqual(block, (EXAMPLES / name).read_bytes().decode("utf-8").replace("\r\n", "\n"))
        self.assertIn("\t", fenced_after(self.readme, "**`examples/products.tsv`**"))

    def test_the_fixtures_are_what_the_readme_says_they_are(self):
        robots = (EXAMPLES / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("User-agent: OAI-SearchBot", robots)
        self.assertIn("User-agent: GPTBot", robots)
        self.assertIn('<div id="root"></div>', (EXAMPLES / "spa-shell.html").read_text(encoding="utf-8"))
        rows = (EXAMPLES / "products.tsv").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 3)  # header + two products

    def test_stated_exit_code_is_the_real_exit_code(self):
        stated = re.search(r"(?m)^Exit code: (\d)$", self.readme)
        self.assertIsNotNone(stated)
        self.assertEqual(int(stated.group(1)), self.code)
        self.assertEqual(self.code, self.json_code)
        self.assertEqual(self.text_err, "")

    def test_text_output_block_is_the_real_stdout(self):
        self.assertEqual(fenced_after(self.readme, TEXT_LABEL), self.text_out)

    def test_json_excerpts_are_contiguous_slices_of_the_real_output(self):
        label = next(l for l in self.readme.splitlines() if l.startswith(JSON_LABEL_PREFIX))
        excerpt = fenced_after(self.readme, label).rstrip("\n").split("\n")
        real = self.json_out.rstrip("\n").split("\n")
        segments, current = [], []
        for line in excerpt:
            if line.strip() == "…":
                segments.append(current)
                current = []
            else:
                current.append(line)
        segments.append(current)
        self.assertGreaterEqual(len(segments), 3, "the trim must be marked with …")
        self.assertTrue(all(segments), "no empty segment")
        pos = 0
        for n, seg in enumerate(segments):
            with self.subTest(segment=n):
                found = next((i for i in range(pos, len(real) - len(seg) + 1)
                              if real[i:i + len(seg)] == seg), None)
                self.assertIsNotNone(found, "excerpt segment is not in the real output, in order")
                pos = found + len(seg)
        # the excerpt carries the parts the README talks about
        joined = "\n".join(excerpt)
        for needle in ('"verdict": "not_ready"', '"token": "OAI-SearchBot"', '"token": "GPTBot"',
                       '"native_commerce"', '"conversational_attributes_coverage_pct"',
                       '"recommendations"'):
            self.assertIn(needle, joined)

    def test_the_readme_commentary_matches_the_run(self):
        # The sentences under the output make factual claims about it.
        summary = re.search(r"Agent readiness: (\w+)", self.text_out).group(1)
        self.assertEqual(summary, "NOT_READY")
        self.assertIn("robots_ai_crawlers: fail", self.text_out)
        self.assertIn("acp_feed: skipped", self.text_out)
        self.assertNotIn("GPTBot", "\n".join(l for l in self.text_out.splitlines() if l.startswith("    ·")))
        self.assertIn("[price] missing on 1/2 products", self.text_out)
        self.assertIn("'Acme Anvil'", self.text_out)


if __name__ == "__main__":
    unittest.main()
