# digital-marketing-pro-agent-readiness

One skill: audit whether AI agents and AI crawlers can actually use a site, with a small offline script that reads the files you export and prints what it found.

This skill reports evidence from a site's own files (its robots.txt, the HTML its server sends, a product feed). It does not predict rankings or citations, it does not decide anyone's crawler policy for them, and it never recommends llms.txt for Google.

It is the agent-readiness audit from Digital Marketing Pro, pulled out as a single Agent Skill that runs on any site with no plugin around it.

## What it checks

- **robots.txt, per AI crawler token**, parsed per RFC 9309: the most specific user-agent group, the longest matching rule, Allow wins ties, `*` and `$` wildcards. Thirteen tokens: OAI-SearchBot, ChatGPT-User, OAI-AdsBot, GPTBot, Claude-SearchBot, Claude-User, ClaudeBot, PerplexityBot, Perplexity-User, Google-Agent, Google-GeminiNotebook, Google-Extended and Applebot-Extended. A robots.txt group that still names Google's retired `Google-NotebookLM` token warns. A blocked search, user-fetch or ads bot fails. Training bots are the owner's policy: reported as info unless you pass `--training-policy allow|block`.
- **Structured data.** Product, Offer, Organization and FAQPage JSON-LD, `@graph` aware. An unparseable block fails; a Product without `offers` warns.
- **No-JavaScript render.** Is the main content in the HTML the server sends? A client-side app shell, very little visible text, or a missing `--expect` phrase fails.
- **Accessibility basics** (warn only): `<html lang>`, image alt text, labelled form fields, named buttons. Cheap proxies for the accessibility tree that browser agents may read.
- **Merchant Center feed** (TSV, CSV or XML with `g:` attributes): the seven required attributes, availability values, price form, how many products opt into checkout on Google with `native_commerce(checkout_eligibility)`, and coverage of the six conversational attributes (`question_and_answer`, `document_link`, `related_product`, `item_group_title`, `variant_option`, `popularity_rank`), which are optional and never fail.
- **Agentic-commerce feed** (optional): the JSONL "OpenAI format" or the Google-compatible CSV/TSV, required fields and the `is_eligible_search` / `is_eligible_checkout` counts.
- **WebMCP** (optional, experimental): declarative form tools and `registerTool` calls. Informational only; it never changes the verdict.

The script is standard-library Python. It makes no network request unless you pass `--fetch`.

## What it never does

- **Never recommends llms.txt for Google.** Google's [AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide) lists "LLMS.txt files and other 'special' markup" under "Mythbusting generative AI search" and says "Google Search itself doesn't use them." The script prints that note on every run, and a test fails if an llms.txt recommendation ever shows up in its output.
- **Never claims structured data is required for AI features.** Google says it isn't. The audit checks JSON-LD because it powers rich results.
- **Never fetches unless you ask.** Everything runs on files you export. `--fetch` is opt-in, and every request it makes is listed in the output. It fetches only public `http`/`https` addresses: redirects are followed by hand and every hop is checked, so loopback, private, link-local and cloud-metadata addresses (and `file://`) are refused.
- **Never decides policy for you.** Whether to block training crawlers and whether to opt products into checkout are the owner's calls.
- **Never says being allowed means being cited.** It checks whether agents can use the site, not whether they do.

## Install

With [skills.sh](https://skills.sh):

```bash
npx skills add indranilbanerjee/digital-marketing-pro-agent-readiness
```

Or copy it by hand. The skill is the folder `skills/agent-readiness-audit`; keep the folder name `agent-readiness-audit`, because the Agent Skills standard requires it to match the skill's `name`.

```bash
git clone https://github.com/indranilbanerjee/digital-marketing-pro-agent-readiness
# Claude Code, for all your projects:
cp -r digital-marketing-pro-agent-readiness/skills/agent-readiness-audit ~/.claude/skills/agent-readiness-audit
# or for one project:
cp -r digital-marketing-pro-agent-readiness/skills/agent-readiness-audit .claude/skills/agent-readiness-audit
```

Any other Agent Skills client: copy `skills/agent-readiness-audit` into that client's skills directory. The script needs Python 3 (tested on 3.11, 3.12 and 3.13) and nothing else.

## Use

Ask in plain language:

- "Can AI agents use our site? Here is robots.txt and the saved HTML of our home page and a product page."
- "Are we blocking GPTBot or ClaudeBot?"
- "Is our product feed ready for AI shopping surfaces? Here is the TSV export."
- "Run an agent-readiness check on https://example.com. You may fetch it."

Save the HTML as the server sends it (`curl -L https://example.com/ > home.html`), not with "Save as" in a browser, which saves the page after JavaScript has run. You get back a verdict, a per-check report with the source for each finding, and a prioritized fix list. Policy questions come back to you as questions.

Or run the script yourself:

```bash
# Offline, on exported files. --path tests more than "/" (repeatable).
python skills/agent-readiness-audit/scripts/agent_readiness_audit.py \
    --robots robots.txt --path /products/ \
    --html home.html --html product.html --expect "Acme Anvil" \
    --feed products.tsv --acp-feed openai-feed.jsonl --webmcp \
    --training-policy either --format json > audit.json

# Live, only when you agree to network access:
python skills/agent-readiness-audit/scripts/agent_readiness_audit.py \
    --site https://example.com --fetch --page https://example.com/products/anvil
```

Exit codes: `0` no check failed (warnings allowed), `1` at least one check failed, `2` bad input (nothing to audit, a missing or unparseable file, a bad flag).

## A real run

Three small fixtures, all in [`examples/`](examples). A robots.txt that blocks OAI-SearchBot and GPTBot:

**`examples/robots.txt`**

```text
User-agent: OAI-SearchBot
User-agent: GPTBot
Disallow: /

User-agent: *
Disallow: /cart/
```

A single-page-app shell, which sends no content without JavaScript:

**`examples/spa-shell.html`**

```text
<!doctype html>
<html>
<head><title>Acme Shop</title></head>
<body>
<div id="root"></div>
<noscript>You need to enable JavaScript to run this app.</noscript>
<script src="/static/js/main.js"></script>
</body>
</html>
```

A two-product feed (the columns are tab-separated):

**`examples/products.tsv`**

```text
id	title	description	link	image_link	availability	price	native_commerce(checkout_eligibility)	question_and_answer
A1	Acme Anvil	Forged steel anvil	https://shop.example/a1	https://shop.example/a1.jpg	in_stock	119.99 USD	TRUE	Q: Weight? A: 55 kg
A2	Acme Hammer	Forging hammer	https://shop.example/a2	https://shop.example/a2.jpg	in_stock		FALSE	
```

Run from the repository root:

```bash
python skills/agent-readiness-audit/scripts/agent_readiness_audit.py \
    --robots examples/robots.txt \
    --html examples/spa-shell.html --expect "Acme Anvil" \
    --feed examples/products.tsv --webmcp --format text
```

Exit code: 1

The output (a real run, unedited):

```text
Agent readiness: NOT_READY  ({'fail': 3, 'warn': 2, 'skipped': 1, 'info': 1})
- robots_ai_crawlers: fail
    · OAI-SearchBot (OpenAI, search) is blocked on / — surfaces websites in ChatGPT search features
- structured_data: warn
    · no Organization (or subtype) JSON-LD on any supplied page
- no_js_render: fail
    · examples/spa-shell.html: only 0 characters of visible text in the server HTML (min 250); client-side app shell detected (root); expected content not in server HTML: 'Acme Anvil'
- accessibility_basics: warn
    · examples/spa-shell.html: no <html lang>
- merchant_feed: fail
    · [price] missing on 1/2 products (required by the product data specification)
- acp_feed: skipped
    · no agentic-commerce feed supplied — optional (use --acp-feed FILE)
- webmcp: info
    · no WebMCP tools declared — optional; nothing to fix unless you are in the origin trial
Recommendations:
  1. Allow OAI-SearchBot in robots.txt if the brand wants to appear in OpenAI answers (surfaces websites in ChatGPT search features).
  2. Fix or add JSON-LD (Organization site-wide; Product with offers on product pages) and validate it in Google's Rich Results Test.
  3. Render the main content (names, prices, key copy) into the server HTML — server-side rendering or pre-rendering.
  4. Fill the missing required Merchant Center attributes before relying on AI shopping surfaces.
Note: llms.txt is NOT recommended for Google: Google's AI optimization guide lists "LLMS.txt files and other 'special' markup" under "Mythbusting generative AI search" — "Google Search itself doesn't use them." (https://developers.google.com/search/docs/fundamentals/ai-optimization-guide, checked 2026-10-04)
```

Read it as a work list. OAI-SearchBot is blocked, so the site will not be surfaced in ChatGPT search features: a fail. GPTBot is blocked too, but that is a training crawler, so under the default policy it is the owner's choice and is not a finding. The page is an app shell with no visible text in the server HTML, and "Acme Anvil" is not in it: a fail. One of the two feed rows has no price: a fail. The `acp_feed` check was skipped because no `--acp-feed` was given.

The same run without `--format text` prints JSON, which is long because it lists every crawler and every tested path. These are the parts that carry the detail (trimmed with …, everything else is the real output):

```json
{
  "tool": "agent-readiness-audit",
  "version": "1.0",
  "sources_checked": "2026-10-04",
  "site": null,
  "fetched": [],
  "verdict": "not_ready",
  "summary": {
    "fail": 3,
    "warn": 2,
    "skipped": 1,
    "info": 1
  },
        …
        {
          "token": "OAI-SearchBot",
          "vendor": "OpenAI",
          "role": "search",
          "purpose": "surfaces websites in ChatGPT search features",
          "verdict": "blocked",
          "paths": {
            "/": {
              "allowed": false,
              "group": "OAI-SearchBot",
              "rule": "Disallow: /"
            }
          },
        …
        {
          "token": "GPTBot",
          "vendor": "OpenAI",
          "role": "training",
          "purpose": "crawls content that may be used to train OpenAI's foundation models",
          "verdict": "blocked",
          "paths": {
            "/": {
              "allowed": false,
              "group": "GPTBot",
              "rule": "Disallow: /"
            }
          },
          "source": "https://developers.openai.com/api/docs/bots"
        },
      …
      "id": "merchant_feed",
      "status": "fail",
      "format": "delimited",
      "products": 2,
      "findings": [
        "[price] missing on 1/2 products (required by the product data specification)"
      ],
      "required_missing": {
        "id": 0,
        "title": 0,
        "description": 0,
        "link": 0,
        "image_link": 0,
        "availability": 0,
        "price": 1
      },
      "native_commerce": {
        "products_opted_in": 1,
        "products_total": 2,
        "attribute": "native_commerce(checkout_eligibility) — boolean, defaults to FALSE",
        "note": "Only listings with native_commerce(checkout_eligibility)=TRUE show the 'Buy' button for checkout on Google; available to select merchants, for products eligible in the United States, Canada and Australia. Also verify (not checkable from a feed): account-level return policy and customer-support contact; consumer_notice where a legal disclaimer / safety warning / Prop 65 notice applies.",
        "sources": [
          "https://support.google.com/merchants/answer/16837055",
          "https://developers.google.com/merchant/ucp/guides/merchant-center"
        ]
      },
      "conversational_attributes_coverage_pct": {
        "question_and_answer": 50.0,
        "document_link": 0.0,
        "related_product": 0.0,
        "item_group_title": 0.0,
        "variant_option": 0.0,
        "popularity_rank": 0.0
      },
  …
  "recommendations": [
    "Allow OAI-SearchBot in robots.txt if the brand wants to appear in OpenAI answers (surfaces websites in ChatGPT search features).",
    "Fix or add JSON-LD (Organization site-wide; Product with offers on product pages) and validate it in Google's Rich Results Test.",
    "Render the main content (names, prices, key copy) into the server HTML — server-side rendering or pre-rendering.",
    "Fill the missing required Merchant Center attributes before relying on AI shopping surfaces."
  ],
```

## What this is not

- **Not a ranking or visibility predictor.** Allowed and well marked up does not mean cited, shown or recommended.
- **Not a rendering test.** The no-JavaScript check reads the HTML as served. It cannot tell you how a JavaScript-capable crawler renders the page.
- **Not Merchant Center's verdict.** It checks a feed file against seven required attributes. Merchant Center diagnostics, account-level return policy and customer-support contact, and UCP onboarding live in the account.
- **Not a guarantee that robots.txt keeps content out.** OpenAI says robots.txt "may not apply" to ChatGPT-User, Perplexity says Perplexity-User "generally ignores robots.txt rules", and Google says the same of its user-triggered fetchers. A CDN can also block crawlers regardless of robots.txt: since 15 Sep 2026, Cloudflare's "Block" setting stops Googlebot, Bingbot and Applebot too.

## Tests

```bash
python -m pytest tests -q
# or, with nothing installed:
python -m unittest discover -s tests -v
```

The tests run the script on inline fixtures (every check, every exit code, the fetch path with a fake server, the claim that nothing touches the network without `--fetch`), check that the skill folder is relocatable and the script imports only the standard library, check that SKILL.md and this README agree with the script (the crawler table, the check ids, the flags, the sources), and re-run the example above to prove it is a real run.

When this repository sits next to a Digital Marketing Pro checkout (`../../digital-marketing-pro`, or set `DMP_DIR`), they also prove **parity**: the script is the same code as `scripts/agent-readiness-audit.py` there (identical syntax tree, and byte-identical outside the module docstring, where only the file name differs), and it prints identical output on a corpus of fixtures and flag combinations. Without that checkout those tests skip.

## Sources

Checked 2026-10-04, the date the script records as `sources_checked`.

- Google AI optimization guide: https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- OpenAI crawlers: https://developers.openai.com/api/docs/bots
- Anthropic crawlers: https://support.claude.com/en/articles/8896518
- Perplexity crawlers: https://docs.perplexity.ai/guides/bots
- Google-Extended: https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers
- Google-Agent and Google-GeminiNotebook (user-triggered fetchers; checked 2026-10-27): https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers
- Applebot-Extended: https://support.apple.com/en-us/119829
- RFC 9309 (robots.txt): https://www.rfc-editor.org/rfc/rfc9309
- Merchant listing markup: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing
- FAQ rich results: https://developers.google.com/search/docs/appearance/structured-data/faqpage
- Product data specification: https://support.google.com/merchants/answer/7052112
- UCP checkout / `native_commerce`: https://support.google.com/merchants/answer/16837055 and https://developers.google.com/merchant/ucp/guides/merchant-center
- Conversational attributes: https://support.google.com/merchants/answer/17085370
- Agentic-commerce feed: https://developers.openai.com/commerce/specs/file-upload/products
- WebMCP: https://developer.chrome.com/docs/ai/webmcp

Crawler and vendor names are factual catalog data taken from those pages. WebMCP is a Chrome origin trial and "under active discussion and subject to change", so treat that check as informational.

## Part of Digital Marketing Pro

This audit comes from [Digital Marketing Pro](https://github.com/indranilbanerjee/digital-marketing-pro), the open-source marketing plugin, where the same script runs inside a brand-aware workflow next to skills for technical SEO, entity audits and AI-visibility follow-up. This repository is the audit alone: no plugin, no brand profile, no other skills.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Indranil Banerjee.
