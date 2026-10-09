"""The standalone audit script, tested on its own. Stdlib unittest only.

Run from the repository root (pytest also works):

    python -m unittest discover -s tests -v
    python -m pytest tests -q

This suite is ported from the Digital Marketing Pro suite that covers the
same script, so the hero repository proves the script's behaviour without
needing that checkout (test_parity.py proves the two copies agree when it is
alongside). Every test runs OFFLINE on inline fixtures; the fetch tests swap
urllib's opener for a fixture server, and a separate test proves that without
--fetch the script never touches the network.

Each class guards one check, and each was proven able to fail by a planted
mutation of the script: first-match instead of longest-match robots rules,
@graph ignored, the visible-text floor disabled, required feed attributes not
counted, ACP required fields skipped, WebMCP absence counted as a failure, the
exit code pinned to 0, and an llms.txt recommendation slipped into the output.

The classes after TestCliContract are specific to this repository: the
skill folder is relocatable, the script imports only the standard library, the
text format and the bundled examples work, and the 5xx robots.txt limitation
that SKILL.md documents is real.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _public_dns():
    """The fetch layer checks every hop with a DNS-resolving guard (public
    addresses only). acme.example is made to resolve to a public address so the
    faked fetches go through; no real DNS lookup happens in these tests. All
    fetches go through ara._http_open, the script's one network call."""
    return mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])

from _fixtures import (
    ACP_JSONL_BAD_LINE, ACP_JSONL_MISSING, ACP_JSONL_OK, FEED_CSV_CLEAN, FEED_TSV,
    FEED_TSV_BAD_PRICE, FEED_TSV_CLEAN, FEED_XML, FEED_XML_BROKEN, HTML_A11Y_ISSUES,
    HTML_BAD_JSONLD, HTML_GOOD, HTML_NO_LANDMARKS, HTML_PRODUCT_NO_OFFER, HTML_SPA_SHELL,
    ROBOTS_BLOCKS_SEARCH, ROBOTS_EMPTY, ROBOTS_OPEN, ROBOTS_TRAINING_BLOCKED,
)
from _support import EXAMPLES, SCRIPT, SKILL, load_module, read, run_json, run_script

ara = load_module("agent_readiness_audit", SCRIPT)


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def write(self, name: str, text: str) -> str:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def audit(self, *args):
        return run_json(*args)

    @staticmethod
    def check(report: dict, cid: str) -> dict:
        return next(c for c in report["checks"] if c["id"] == cid)


class TestRobotsMatching(unittest.TestCase):
    """RFC 9309 semantics — the plant (first-match instead of longest-match)
    flipped test_longest_match_wins and test_allow_wins_a_tie."""

    def test_longest_match_wins(self):
        g = ara.parse_robots("User-agent: *\nDisallow: /shop\nAllow: /shop/public\n")
        self.assertTrue(ara.is_allowed(g, "GPTBot", "/shop/public/x")[0])
        self.assertFalse(ara.is_allowed(g, "GPTBot", "/shop/private")[0])

    def test_allow_wins_a_tie(self):
        g = ara.parse_robots("User-agent: *\nDisallow: /page\nAllow: /page\n")
        self.assertTrue(ara.is_allowed(g, "ClaudeBot", "/page")[0])

    def test_named_group_overrides_star(self):
        g = ara.parse_robots("User-agent: *\nDisallow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n")
        self.assertTrue(ara.is_allowed(g, "OAI-SearchBot", "/")[0])
        self.assertFalse(ara.is_allowed(g, "PerplexityBot", "/")[0])

    def test_token_match_is_case_insensitive_and_groups_merge(self):
        g = ara.parse_robots("user-agent: gptbot\nDisallow: /a\n\nUser-Agent: GPTBot\nDisallow: /b\n")
        self.assertFalse(ara.is_allowed(g, "GPTBot", "/a")[0])
        self.assertFalse(ara.is_allowed(g, "GPTBot", "/b")[0])

    def test_wildcards_and_end_anchor(self):
        g = ara.parse_robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/\n")
        self.assertFalse(ara.is_allowed(g, "ClaudeBot", "/files/guide.pdf")[0])
        self.assertTrue(ara.is_allowed(g, "ClaudeBot", "/files/guide.pdf?x=1")[0])
        self.assertFalse(ara.is_allowed(g, "ClaudeBot", "/tmp123/x")[0])

    def test_empty_disallow_allows_everything(self):
        g = ara.parse_robots("User-agent: *\nDisallow:\n")
        self.assertTrue(ara.is_allowed(g, "GPTBot", "/anything")[0])

    def test_no_robots_rules_means_allowed(self):
        self.assertTrue(ara.is_allowed([], "Claude-User", "/")[0])

    def test_rules_before_any_user_agent_are_ignored(self):
        g = ara.parse_robots("Disallow: /\nUser-agent: *\nDisallow: /x\n")
        self.assertTrue(ara.is_allowed(g, "GPTBot", "/")[0])

    def test_comments_and_blank_lines_are_skipped(self):
        g = ara.parse_robots("# note\nUser-agent: GPTBot # inline\n\nDisallow: /a # why\n")
        self.assertFalse(ara.is_allowed(g, "GPTBot", "/a")[0])

    def test_crawler_list_covers_the_verified_tokens(self):
        tokens = {b["token"] for b in ara.AI_CRAWLERS}
        for t in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "OAI-AdsBot", "ClaudeBot",
                  "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User",
                  "Google-Extended", "Applebot-Extended"):
            self.assertIn(t, tokens)
        for b in ara.AI_CRAWLERS:
            self.assertTrue(b["source"].startswith("https://"), b["token"])


class TestRobotsVerdicts(_Tmp):
    def test_blocking_answer_engines_fails(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_BLOCKS_SEARCH))
        c = self.check(rep, "robots_ai_crawlers")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(code, 1)
        joined = " ".join(c["findings"])
        self.assertIn("OAI-SearchBot", joined)
        self.assertIn("PerplexityBot", joined)
        self.assertNotIn("GPTBot", joined, "training bots are policy, not a failure, by default")

    def test_training_blocks_are_policy_by_default(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_TRAINING_BLOCKED))
        c = self.check(rep, "robots_ai_crawlers")
        self.assertEqual(c["status"], "pass")
        self.assertEqual(code, 0)
        gpt = next(b for b in c["crawlers"] if b["token"] == "GPTBot")
        self.assertEqual(gpt["verdict"], "blocked")

    def test_training_policy_allow_turns_blocks_into_failures(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_TRAINING_BLOCKED),
                               "--training-policy", "allow")
        self.assertEqual(self.check(rep, "robots_ai_crawlers")["status"], "fail")
        self.assertEqual(code, 1)

    def test_training_policy_block_fails_when_a_training_bot_is_not_blocked(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN),
                               "--training-policy", "block")
        c = self.check(rep, "robots_ai_crawlers")
        self.assertEqual(c["status"], "fail")
        self.assertIn("--training-policy is 'block'", " ".join(c["findings"]))
        self.assertEqual(code, 1)

    def test_partial_block_on_a_tested_path(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN), "--path", "/cart/")
        c = self.check(rep, "robots_ai_crawlers")
        bot = next(b for b in c["crawlers"] if b["token"] == "OAI-SearchBot")
        self.assertEqual(bot["verdict"], "partially_blocked")
        self.assertEqual(c["status"], "fail")

    def test_root_is_always_tested_first(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN), "--path", "/products/")
        bot = self.check(rep, "robots_ai_crawlers")["crawlers"][0]
        self.assertEqual(list(bot["paths"]), ["/", "/products/"])

    def test_empty_robots_is_reported_not_silently_passed(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_EMPTY))
        c = self.check(rep, "robots_ai_crawlers")
        self.assertEqual(c["status"], "pass")
        self.assertIn("robots.txt is empty", " ".join(c["findings"]))

    def test_user_fetchers_carry_the_vendor_robots_caveat(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN))
        c = self.check(rep, "robots_ai_crawlers")
        for token in ("ChatGPT-User", "Perplexity-User"):
            bot = next(b for b in c["crawlers"] if b["token"] == token)
            self.assertIn("robots", bot["note"].lower())


class TestStructuredData(_Tmp):
    """Plant: ignoring @graph made test_graph_is_walked fail."""

    def test_graph_is_walked(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD))
        c = self.check(rep, "structured_data")
        self.assertEqual(c["present"], {"Product": True, "Offer": True,
                                        "Organization": True, "FAQPage": False})
        self.assertEqual(c["status"], "pass")

    def test_unparseable_jsonld_fails(self):
        rep, code = self.audit("--html", self.write("p.html", HTML_BAD_JSONLD))
        c = self.check(rep, "structured_data")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(code, 1)
        self.assertIn("unparseable", c["findings"][0])

    def test_product_without_offers_warns(self):
        rep, code = self.audit("--html", self.write("p.html", HTML_PRODUCT_NO_OFFER))
        c = self.check(rep, "structured_data")
        self.assertEqual(c["status"], "warn")
        self.assertEqual(code, 0, "a warning alone must not fail the run")

    def test_missing_organization_warns(self):
        rep, _ = self.audit("--html", self.write("s.html", HTML_SPA_SHELL))
        c = self.check(rep, "structured_data")
        self.assertEqual(c["status"], "warn")
        self.assertIn("no Organization", " ".join(c["findings"]))

    def test_faqpage_note_says_rich_results_are_restricted(self):
        html = ('<html lang="en"><head><script type="application/ld+json">'
                '{"@graph":[{"@type":"Organization","name":"A"},{"@type":"FAQPage"}]}'
                '</script></head><body><main><h1>FAQ</h1><p>' + "Answer text. " * 30 + "</p></main></body></html>")
        rep, _ = self.audit("--html", self.write("f.html", html))
        c = self.check(rep, "structured_data")
        self.assertTrue(c["present"]["FAQPage"])
        self.assertIn("authoritative government and health", " ".join(c["notes"]))

    def test_ai_note_says_markup_is_not_required_for_ai(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD))
        self.assertIn("isn't required for generative AI search",
                      " ".join(self.check(rep, "structured_data")["notes"]))


class TestNoJsRender(_Tmp):
    """Plant: disabling the visible-text floor made test_spa_shell_fails fail."""

    def test_spa_shell_fails(self):
        rep, code = self.audit("--html", self.write("s.html", HTML_SPA_SHELL))
        c = self.check(rep, "no_js_render")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(code, 1)
        self.assertTrue(c["pages"][0]["noscript_says_enable_js"])
        self.assertIn("root", c["pages"][0]["spa_shell_markers"])

    def test_server_rendered_page_passes(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD), "--expect", "Acme Anvil")
        self.assertEqual(self.check(rep, "no_js_render")["status"], "pass")

    def test_missing_expected_text_fails(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD), "--expect", "Titanium Hammer")
        c = self.check(rep, "no_js_render")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["pages"][0]["missing_expected"], ["Titanium Hammer"])

    def test_min_text_flag_moves_the_floor(self):
        path = self.write("p.html", HTML_GOOD)
        rep, _ = self.audit("--html", path, "--min-text", "100000")
        self.assertEqual(self.check(rep, "no_js_render")["status"], "fail")
        rep, _ = self.audit("--html", path, "--min-text", "10")
        self.assertEqual(self.check(rep, "no_js_render")["status"], "pass")

    def test_page_without_h1_or_main_warns(self):
        rep, code = self.audit("--html", self.write("n.html", HTML_NO_LANDMARKS))
        self.assertEqual(self.check(rep, "no_js_render")["status"], "warn")
        self.assertEqual(code, 0)

    def test_text_inside_scripts_does_not_count(self):
        html = "<html><body><script>" + ("var s='lots of text';" * 200) + "</script></body></html>"
        p = ara.parse_html(html)
        self.assertEqual(p.visible_text(), "")

    def test_unclosed_head_does_not_hide_the_body(self):
        p = ara.parse_html("<html><head><title>x</title><meta charset=utf-8><body><p>Hello world</p>")
        self.assertEqual(p.visible_text(), "Hello world")


class TestAccessibilityBasics(_Tmp):
    def test_issues_warn_never_fail(self):
        rep, code = self.audit("--html", self.write("a.html", HTML_A11Y_ISSUES))
        c = self.check(rep, "accessibility_basics")
        self.assertEqual(c["status"], "warn")
        joined = " ".join(c["findings"])
        for needle in ("lang", "alt", "label", "accessible name"):
            self.assertIn(needle, joined)

    def test_clean_page_passes(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD))
        self.assertEqual(self.check(rep, "accessibility_basics")["status"], "pass")


class TestMerchantFeed(_Tmp):
    """Plant: not counting required attributes made test_missing_required_fails fail."""

    def test_missing_required_fails(self):
        rep, code = self.audit("--feed", self.write("f.tsv", FEED_TSV))
        c = self.check(rep, "merchant_feed")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(code, 1)
        self.assertEqual(c["required_missing"]["price"], 1)
        joined = " ".join(c["findings"])
        self.assertIn("[availability]", joined)
        self.assertIn("not TRUE/FALSE", joined)

    def test_native_commerce_and_conversational_attributes(self):
        rep, _ = self.audit("--feed", self.write("f.tsv", FEED_TSV))
        c = self.check(rep, "merchant_feed")
        self.assertEqual(c["native_commerce"]["products_opted_in"], 1)
        self.assertIn("United States, Canada and Australia", c["native_commerce"]["note"])
        self.assertAlmostEqual(c["conversational_attributes_coverage_pct"]["question_and_answer"], 33.3)

    def test_xml_feed_with_nested_native_commerce(self):
        rep, code = self.audit("--feed", self.write("f.xml", FEED_XML))
        c = self.check(rep, "merchant_feed")
        self.assertEqual(c["format"], "xml")
        self.assertEqual(c["status"], "pass")
        self.assertEqual(c["native_commerce"]["products_opted_in"], 1)
        self.assertEqual(c["conversational_attributes_coverage_pct"]["popularity_rank"], 100.0)
        self.assertEqual(code, 0)

    def test_clean_feed_passes(self):
        rep, code = self.audit("--feed", self.write("f.tsv", FEED_TSV_CLEAN))
        self.assertEqual(self.check(rep, "merchant_feed")["status"], "pass")
        self.assertEqual(code, 0)

    def test_csv_feed_is_read(self):
        rep, _ = self.audit("--feed", self.write("f.csv", FEED_CSV_CLEAN))
        c = self.check(rep, "merchant_feed")
        self.assertEqual((c["status"], c["products"]), ("pass", 1))

    def test_price_not_in_number_currency_form_warns(self):
        rep, code = self.audit("--feed", self.write("f.tsv", FEED_TSV_BAD_PRICE))
        c = self.check(rep, "merchant_feed")
        self.assertEqual(c["status"], "warn")
        self.assertIn("NUMBER CUR", " ".join(c["findings"]))
        self.assertEqual(code, 0)

    def test_no_native_commerce_is_reported_not_failed(self):
        rep, _ = self.audit("--feed", self.write("f.tsv", FEED_TSV_CLEAN))
        c = self.check(rep, "merchant_feed")
        self.assertEqual(c["native_commerce"]["products_opted_in"], 0)
        self.assertIn("no product opts into checkout", " ".join(c["findings"]))
        self.assertEqual(c["status"], "pass")


class TestAcpFeed(_Tmp):
    """Plant: skipping the ACP required-field check made test_missing_field_fails fail."""

    def test_optional_and_skipped_when_absent(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN))
        c = self.check(rep, "acp_feed")
        self.assertEqual(c["status"], "skipped")
        self.assertTrue(c["optional"])

    def test_complete_jsonl_passes(self):
        rep, _ = self.audit("--acp-feed", self.write("o.jsonl", ACP_JSONL_OK))
        c = self.check(rep, "acp_feed")
        self.assertEqual((c["status"], c["format"], c["eligible_search"]), ("pass", "jsonl", 1))

    def test_missing_field_fails(self):
        rep, code = self.audit("--acp-feed", self.write("o.jsonl", ACP_JSONL_MISSING))
        c = self.check(rep, "acp_feed")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["required_missing"]["seller_name"], 1)
        self.assertEqual(code, 1)

    def test_google_compatible_csv_is_accepted(self):
        rep, _ = self.audit("--acp-feed", self.write("o.csv", FEED_CSV_CLEAN))
        c = self.check(rep, "acp_feed")
        self.assertEqual((c["status"], c["format"]), ("pass", "delimited"))

    def test_jsonl_with_a_broken_line_is_bad_input(self):
        rep, code = self.audit("--acp-feed", self.write("o.jsonl", ACP_JSONL_BAD_LINE))
        self.assertEqual(code, 2)
        self.assertIn("not JSON", rep["error"])


class TestWebMcpIsExperimental(_Tmp):
    """Plant: counting WebMCP absence as a failure made test_absence_never_fails fail."""

    def test_detects_declarative_tool(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD), "--webmcp")
        c = self.check(rep, "webmcp")
        self.assertEqual(c["status"], "info")
        self.assertTrue(c["experimental"])
        self.assertEqual(c["declarative_forms"][0]["toolname"], "checkStock")
        self.assertEqual(c["toolparamdescription_fields"], 1)
        self.assertIn("origin trial", c["status_note"])

    def test_detects_imperative_registration(self):
        html = ('<html lang="en"><body><main><h1>x</h1><p>' + "text " * 80 + "</p></main>"
                "<script>navigator.modelContext.registerTool({name:'a'});</script></body></html>")
        rep, _ = self.audit("--html", self.write("p.html", html), "--webmcp")
        self.assertEqual(self.check(rep, "webmcp")["imperative_register_calls"], 1)

    def test_absence_never_fails(self):
        rep, code = self.audit("--html", self.write("p.html", HTML_PRODUCT_NO_OFFER), "--webmcp")
        self.assertEqual(self.check(rep, "webmcp")["status"], "info")
        self.assertEqual(code, 0)

    def test_skipped_unless_requested(self):
        rep, _ = self.audit("--html", self.write("p.html", HTML_GOOD))
        self.assertEqual(self.check(rep, "webmcp")["status"], "skipped")


class TestNoLlmsTxtForGoogle(_Tmp):
    """Plant: adding an 'add llms.txt' recommendation made this fail."""

    def test_never_recommends_llms_txt_and_says_why(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_BLOCKS_SEARCH),
                            "--html", self.write("s.html", HTML_SPA_SHELL),
                            "--feed", self.write("f.tsv", FEED_TSV))
        self.assertTrue(rep["recommendations"], "fixture should produce recommendations")
        for r in rep["recommendations"]:
            self.assertNotIn("llms", r.lower())
        self.assertIn("Google Search itself doesn't use them", rep["notes"][0])
        self.assertIn("NOT recommended for Google", rep["notes"][0])

    def test_the_note_is_in_the_text_format_too(self):
        code, out, _ = run_script("--robots", self.write("r.txt", ROBOTS_OPEN), "--format", "text")
        self.assertIn("llms.txt is NOT recommended for Google", out)


class TestCliContract(_Tmp):
    """Exit codes 0/1/2 + JSON. Plant: pinning the exit code to 0 made
    test_failure_exits_1 fail."""

    def test_clean_run_exits_0(self):
        rep, code = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN),
                               "--html", self.write("p.html", HTML_GOOD))
        self.assertEqual(code, 0)
        self.assertEqual(rep["verdict"], "ready")

    def test_warnings_only_is_needs_work_and_exits_0(self):
        rep, code = self.audit("--html", self.write("p.html", HTML_PRODUCT_NO_OFFER))
        self.assertEqual(rep["verdict"], "needs_work")
        self.assertEqual(code, 0)

    def test_failure_exits_1(self):
        rep, code = self.audit("--html", self.write("s.html", HTML_SPA_SHELL))
        self.assertEqual(code, 1)
        self.assertEqual(rep["verdict"], "not_ready")

    def test_nothing_to_audit_exits_2(self):
        rep, code = self.audit()
        self.assertEqual(code, 2)
        self.assertIn("nothing to audit", rep["error"])

    def test_missing_file_exits_2(self):
        rep, code = self.audit("--robots", str(self.dir / "nope.txt"))
        self.assertEqual(code, 2)
        self.assertIn("not found", rep["error"])

    def test_non_utf8_file_exits_2(self):
        p = self.dir / "bad.txt"
        p.write_bytes(b"User-agent: *\n\xff\xfe\n")
        rep, code = self.audit("--robots", str(p))
        self.assertEqual(code, 2)
        self.assertIn("not UTF-8", rep["error"])

    def test_broken_xml_feed_exits_2(self):
        rep, code = self.audit("--feed", self.write("f.xml", FEED_XML_BROKEN))
        self.assertEqual(code, 2)
        self.assertIn("does not parse", rep["error"])

    def test_bad_flag_exits_2(self):
        _, code = self.audit("--training-policy", "sometimes")
        self.assertEqual(code, 2)

    def test_fetch_requires_site(self):
        rep, code = self.audit("--fetch")
        self.assertEqual(code, 2)

    def test_fetch_rejects_a_non_http_site(self):
        rep, code = self.audit("--fetch", "--site", "ftp://acme.example")
        self.assertEqual(code, 2)
        self.assertIn("http(s)", rep["error"])

    def test_report_shape(self):
        rep, _ = self.audit("--robots", self.write("r.txt", ROBOTS_OPEN))
        self.assertEqual(list(rep), ["tool", "version", "sources_checked", "site", "fetched",
                                     "verdict", "summary", "checks", "recommendations", "notes"])
        self.assertEqual([c["id"] for c in rep["checks"]],
                         ["robots_ai_crawlers", "structured_data", "no_js_render",
                          "accessibility_basics", "merchant_feed", "acp_feed", "webmcp"])
        self.assertEqual(rep["sources_checked"], ara.CHECKED)


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


class TestFetchIsOptIn(unittest.TestCase):
    def test_offline_run_never_touches_the_network(self):
        with tempfile.TemporaryDirectory() as td:
            robots = Path(td) / "r.txt"
            robots.write_text(ROBOTS_OPEN, encoding="utf-8")
            # fetch() swallows exceptions by design, so record calls instead
            # of raising — a raise would be eaten and the test could not fail.
            with mock.patch.object(ara, "_http_open") as urlopen:
                with mock.patch("sys.stdout"):
                    code = ara.main(["--robots", str(robots), "--site", "https://acme.example"])
        urlopen.assert_not_called()
        self.assertEqual(code, 0)

    def test_fetch_reads_robots_and_pages(self):
        served = {"https://acme.example/robots.txt": ROBOTS_BLOCKS_SEARCH,
                  "https://acme.example": HTML_GOOD}

        def fake_urlopen(req, timeout=15):
            return _FakeResp(served[req.full_url])

        with mock.patch.object(ara, "_http_open", side_effect=fake_urlopen), _public_dns():
            args = ara.build_parser().parse_args(["--site", "https://acme.example", "--fetch"])
            rep = ara.run_audit(args)
        self.assertEqual(len(rep["fetched"]), 2)
        self.assertEqual(self.check_status(rep, "robots_ai_crawlers"), "fail")
        self.assertEqual(self.check_status(rep, "structured_data"), "pass")

    def test_robots_404_means_allow_all(self):
        def fake_urlopen(req, timeout=15):
            if req.full_url.endswith("/robots.txt"):
                raise ara.urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
            return _FakeResp(HTML_GOOD)

        with mock.patch.object(ara, "_http_open", side_effect=fake_urlopen), _public_dns():
            args = ara.build_parser().parse_args(["--site", "https://acme.example", "--fetch"])
            rep = ara.run_audit(args)
        self.assertEqual(self.check_status(rep, "robots_ai_crawlers"), "pass")

    def test_extra_pages_are_fetched(self):
        seen = []

        def fake_urlopen(req, timeout=15):
            seen.append(req.full_url)
            if req.full_url.endswith("/robots.txt"):
                return _FakeResp(ROBOTS_OPEN)
            return _FakeResp(HTML_GOOD)

        with mock.patch.object(ara, "_http_open", side_effect=fake_urlopen), _public_dns():
            args = ara.build_parser().parse_args(
                ["--site", "https://acme.example", "--fetch", "--page", "https://acme.example/p/anvil"])
            ara.run_audit(args)
        self.assertEqual(seen, ["https://acme.example/robots.txt", "https://acme.example",
                                "https://acme.example/p/anvil"])

    @staticmethod
    def check_status(rep, cid):
        return next(c for c in rep["checks"] if c["id"] == cid)["status"]


# ---------------------------------------------------------------------------
# Specific to this repository
# ---------------------------------------------------------------------------

class TestStandaloneSkill(_Tmp):
    def test_skill_folder_is_relocatable(self):
        # The script reads nothing relative to itself, so it works wherever an
        # agent client copies the skill folder.
        moved = self.dir / "elsewhere" / "agent-readiness-audit"
        shutil.copytree(SKILL, moved, ignore=shutil.ignore_patterns("__pycache__"))
        args = ("--robots", self.write("r.txt", ROBOTS_BLOCKS_SEARCH),
                "--html", self.write("p.html", HTML_GOOD), "--feed", self.write("f.tsv", FEED_TSV))
        here, code_here = run_json(*args, cwd=self.dir)
        there, code_there = run_json(*args, cwd=self.dir,
                                     script=moved / "scripts" / "agent_readiness_audit.py")
        self.assertEqual((code_here, here), (code_there, there))

    def test_script_is_stdlib_only(self):
        tree = ast.parse(read(SCRIPT))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "argparse", "csv", "html", "io", "ipaddress", "json",
                                        "pathlib", "re", "socket", "sys", "urllib", "xml"})

    def test_script_does_not_write_files(self):
        # The audit only reads. A write call anywhere in the source would be a
        # behaviour change worth a conversation.
        src = read(SCRIPT)
        for needle in (".write_text(", ".write_bytes(", "os.remove", "shutil."):
            self.assertNotIn(needle, src, needle)
        self.assertIsNone(re.search(r"(?<![\w.])open\(", src), "builtin open() is not used")

    def test_text_format_is_a_short_readable_summary(self):
        code, out, _ = run_script("--robots", self.write("r.txt", ROBOTS_BLOCKS_SEARCH),
                                  "--format", "text")
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Agent readiness: NOT_READY"))
        self.assertIn("- robots_ai_crawlers: fail", lines)
        self.assertIn("Recommendations:", lines)
        self.assertTrue(lines[-1].startswith("Note: llms.txt is NOT recommended for Google"))
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_help_exits_0_and_lists_the_documented_flags(self):
        code, out, _ = run_script("--help")
        self.assertEqual(code, 0)
        for flag in ("--site", "--fetch", "--page", "--robots", "--path", "--training-policy",
                     "--html", "--expect", "--min-text", "--feed", "--acp-feed", "--webmcp",
                     "--format"):
            self.assertIn(flag, out)

    def test_bundled_examples_give_the_documented_result(self):
        # The README's real run; test_readme.py checks the README text itself.
        rep, code = run_json("--robots", "examples/robots.txt", "--html", "examples/spa-shell.html",
                             "--expect", "Acme Anvil", "--feed", "examples/products.tsv",
                             "--webmcp", cwd=EXAMPLES.parent)
        self.assertEqual(code, 1)
        self.assertEqual(rep["verdict"], "not_ready")
        by_id = {c["id"]: c for c in rep["checks"]}
        self.assertEqual({k: v["status"] for k, v in by_id.items()},
                         {"robots_ai_crawlers": "fail", "structured_data": "warn",
                          "no_js_render": "fail", "accessibility_basics": "warn",
                          "merchant_feed": "fail", "acp_feed": "skipped", "webmcp": "info"})
        blocked = {b["token"] for b in by_id["robots_ai_crawlers"]["crawlers"]
                   if b["verdict"] == "blocked"}
        self.assertEqual(blocked, {"OAI-SearchBot", "GPTBot"})


class TestUnreachableRobots(unittest.TestCase):
    """SKILL.md caveat 5: per RFC 9309 a 4xx robots.txt means allow-all and a
    5xx means complete disallow, so a 5xx fails the robots check with a finding
    that says why. If the script's handling changes, the caveat must change too."""

    def _audit(self, robots_status):
        def fake_urlopen(req, timeout=15):
            if req.full_url.endswith("/robots.txt"):
                raise ara.urllib.error.HTTPError(req.full_url, robots_status, "x", {}, None)
            return _FakeResp(HTML_GOOD)

        with mock.patch.object(ara, "_http_open", side_effect=fake_urlopen), _public_dns():
            args = ara.build_parser().parse_args(["--site", "https://acme.example", "--fetch"])
            return ara.run_audit(args)

    def test_503_robots_means_complete_disallow_and_the_status_is_in_the_fetch_log(self):
        rep = self._audit(503)
        robots = next(c for c in rep["checks"] if c["id"] == "robots_ai_crawlers")
        self.assertEqual(robots["status"], "fail")
        self.assertIn("RFC 9309", robots["findings"][0])
        self.assertTrue(all(b["verdict"] == "blocked" for b in robots["crawlers"]))
        self.assertEqual(rep["fetched"][0], {"url": "https://acme.example/robots.txt",
                                             "status": 503, "error": "HTTP 503"})

    def test_4xx_robots_is_treated_as_allow_all(self):
        rep = self._audit(410)
        robots = next(c for c in rep["checks"] if c["id"] == "robots_ai_crawlers")
        self.assertEqual(robots["status"], "pass")
        self.assertIn("treated as allow-all", robots["source"])

    def test_the_user_agent_is_the_documented_one(self):
        seen = []

        def fake_urlopen(req, timeout=15):
            seen.append(req.get_header("User-agent"))
            return _FakeResp(ROBOTS_OPEN if req.full_url.endswith("/robots.txt") else HTML_GOOD)

        with mock.patch.object(ara, "_http_open", side_effect=fake_urlopen), _public_dns():
            ara.run_audit(ara.build_parser().parse_args(["--site", "https://acme.example", "--fetch"]))
        self.assertEqual(set(seen), {ara.USER_AGENT})
        self.assertTrue(ara.USER_AGENT.startswith("DMP-agent-readiness-audit/1.0"))


if __name__ == "__main__":
    unittest.main()
