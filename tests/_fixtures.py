"""Inline fixtures shared by the audit tests and the parity tests.

Everything here is small, invented data (example domains, a made-up Acme
catalogue). Nothing is fetched and nothing is real.
"""
from __future__ import annotations

import json

ROBOTS_OPEN = """\
User-agent: *
Disallow: /cart/
"""

ROBOTS_BLOCKS_SEARCH = """\
User-agent: OAI-SearchBot
User-agent: PerplexityBot
Disallow: /

User-agent: GPTBot
Disallow: /

User-agent: *
Allow: /
"""

ROBOTS_TRAINING_BLOCKED = """\
User-agent: GPTBot
User-agent: ClaudeBot
User-agent: Google-Extended
User-agent: Applebot-Extended
Disallow: /

User-agent: *
Disallow:
"""

ROBOTS_EMPTY = ""

HTML_GOOD = """<!doctype html><html lang="en"><head><title>Acme Anvil</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Organization","name":"Acme","url":"https://acme.example"},
 {"@type":"Product","name":"Acme Anvil","image":"https://acme.example/a.jpg",
  "offers":{"@type":"Offer","price":"119.99","priceCurrency":"USD",
            "availability":"https://schema.org/InStock"}}]}
</script></head>
<body><main><h1>Acme Anvil</h1>
<p>The Acme Anvil is a forged steel anvil for hobby and professional smiths. It weighs
55 kg, ships flat-packed on a pallet and comes with a ten-year warranty against cracks.
Price: 119.99 USD. In stock and ready to ship from our Ohio warehouse within two days.</p>
<img src="a.jpg" alt="Acme Anvil on a workbench">
<form toolname="checkStock" tooldescription="Check stock for a product SKU" action="/stock">
<label for="sku">SKU</label><input id="sku" name="sku"
 toolparamdescription="The product SKU to look up"><button type="submit">Check</button></form>
</main></body></html>"""

HTML_SPA_SHELL = """<!doctype html><html lang="en"><head><title>Shop</title></head>
<body><div id="root"></div><noscript>You need to enable JavaScript to run this app.</noscript>
<script src="/static/js/main.js"></script></body></html>"""

HTML_BAD_JSONLD = """<html lang="en"><head>
<script type="application/ld+json">{"@type": "Organization", "name": "Acme",}</script>
</head><body><main><h1>About Acme</h1><p>""" + ("Acme makes anvils. " * 30) + """</p></main></body></html>"""

HTML_PRODUCT_NO_OFFER = """<html lang="en"><head>
<script type="application/ld+json">[{"@type":"Organization","name":"Acme"},
{"@type":"Product","name":"Widget","image":"w.jpg"}]</script>
</head><body><main><h1>Widget</h1><p>""" + ("A very good widget for every workshop. " * 12) + """</p></main></body></html>"""

HTML_A11Y_ISSUES = ('<html><body><main><h1>x</h1><img src="a.png"><input name="q">'
                    '<button></button><p>' + "text " * 80 + "</p></main></body></html>")

HTML_NO_LANDMARKS = "<html lang=\"en\"><body><p>" + ("Plain paragraph text with no heading. " * 12) + "</p></body></html>"

FEED_TSV = (
    "id\ttitle\tdescription\tlink\timage_link\tavailability\tprice\tbrand\t"
    "native_commerce(checkout_eligibility)\tquestion_and_answer\n"
    "A1\tAnvil\tForged anvil\thttps://a.example/a1\thttps://a.example/a1.jpg\tin_stock\t119.99 USD\tAcme\tTRUE\tQ: weight? A: 55 kg\n"
    "A2\tHammer\tForging hammer\thttps://a.example/a2\thttps://a.example/a2.jpg\tin_stock\t\tAcme\tFALSE\t\n"
    "A3\tTongs\tTongs\thttps://a.example/a3\thttps://a.example/a3.jpg\tsold out\t19.00 USD\tAcme\tmaybe\t\n"
)

FEED_TSV_CLEAN = (
    "id\ttitle\tdescription\tlink\timage_link\tavailability\tprice\tbrand\n"
    "A1\tAnvil\tForged anvil\thttps://a.example/a1\thttps://a.example/a1.jpg\tin_stock\t119.99 USD\tAcme\n"
)

FEED_TSV_BAD_PRICE = (
    "id\ttitle\tdescription\tlink\timage_link\tavailability\tprice\n"
    "A1\tAnvil\tForged anvil\thttps://a.example/a1\thttps://a.example/a1.jpg\tin_stock\t$119\n"
)

FEED_CSV_CLEAN = (
    "id,title,description,link,image_link,availability,price,brand\n"
    "A1,Anvil,Forged anvil,https://a.example/a1,https://a.example/a1.jpg,in_stock,119.99 USD,Acme\n"
)

FEED_XML = """<?xml version="1.0"?>
<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0"><channel>
<item><g:id>A1</g:id><title>Anvil</title><description>Forged anvil</description>
<link>https://a.example/a1</link><g:image_link>https://a.example/a1.jpg</g:image_link>
<g:availability>in_stock</g:availability><g:price>119.99 USD</g:price><g:brand>Acme</g:brand>
<g:native_commerce><g:checkout_eligibility>TRUE</g:checkout_eligibility></g:native_commerce>
<g:popularity_rank>5</g:popularity_rank></item>
</channel></rss>"""

FEED_XML_BROKEN = "<rss><channel><item><id>A1</id></channel></rss>"

ACP_JSONL_OK = "\n".join(json.dumps(r) for r in [
    {"item_id": "A1", "title": "Anvil", "description": "Forged", "url": "https://a.example/a1",
     "brand": "Acme", "seller_name": "Acme", "image_url": "https://a.example/a1.jpg",
     "availability": "in_stock", "price": "119.99 USD", "is_eligible_search": True},
])

ACP_JSONL_MISSING = json.dumps({"item_id": "A1", "title": "Anvil", "description": "Forged",
                                "url": "https://a.example/a1", "brand": "Acme",
                                "image_url": "https://a.example/a1.jpg",
                                "availability": "in_stock", "price": "119.99 USD"})

ACP_JSONL_BAD_LINE = ACP_JSONL_OK + "\n{not json}\n"
