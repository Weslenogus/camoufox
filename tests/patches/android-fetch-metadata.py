"""
Verify request metadata headers (patches/android/android-21-fetch-metadata.patch
has no browser patch; the change is the profile's headers and prefs).

With {"device:profile": "pixel10"}, requests carry what Chrome on Android
sends:

  * the document: Chrome's navigation Accept header,
    Upgrade-Insecure-Requests 1, Sec-Fetch-Dest document, Sec-Fetch-Mode
    navigate;
  * an <img>: Chrome's image Accept header, Sec-Fetch-Dest image,
    Sec-Fetch-Mode no-cors, Sec-Fetch-Site same-origin;
  * a same-origin fetch(): Sec-Fetch-Mode cors, Sec-Fetch-Site same-origin,
    and no Origin header (a same-origin GET carries none);
  * a cross-site fetch(): Origin set to the page's origin, Sec-Fetch-Site
    cross-site;
  * the client hints, including Sec-CH-UA-Form-Factors "Mobile", on every
    request to a potentially trustworthy origin.

The control launch keeps Firefox's own Accept headers and sends no client
hints.

Run:
    python tests/patches/android-fetch-metadata.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

NAV_ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7")
IMG_ACCEPT = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"

PAGE = """<!doctype html><title>metadata</title><img src="/img.png">"""


async def probe(binary, config):
    other = PageServer({"/cross.txt": ("text/plain", "ok")})
    with other:
        cross = other.url("/cross.txt").replace("localhost", "127.0.0.1")
        with PageServer({"/": ("text/html", PAGE), "/img.png": ("image/png", ""),
                         "/same.txt": ("text/plain", "ok")}) as server:
            async with launch_raw(binary, config) as page:
                await page.goto(server.url("/"))
                await page.evaluate(
                    "async (cross) => { await fetch('/same.txt');"
                    " try { await fetch(cross); } catch (e) {} }", cross)
                await page.wait_for_timeout(500)
            origin = server.url("/").rstrip("/")
            return server, other, origin


def first(server, path):
    found = server.headers_for(path)
    return found[0] if found else {}


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    server, other, origin = await probe(binary, PIXEL10)
    doc, img = first(server, "/"), first(server, "/img.png")
    same, cross = first(server, "/same.txt"), first(other, "/cross.txt")
    ok = compare({
        "document accept": doc.get("accept"),
        "document upgrade-insecure-requests": doc.get("upgrade-insecure-requests"),
        "document sec-fetch-dest/mode": (doc.get("sec-fetch-dest"), doc.get("sec-fetch-mode")),
        "image accept": img.get("accept"),
        "image sec-fetch-*": (img.get("sec-fetch-dest"), img.get("sec-fetch-mode"),
                              img.get("sec-fetch-site")),
        "same-origin fetch sec-fetch-*": (same.get("sec-fetch-dest"), same.get("sec-fetch-mode"),
                                          same.get("sec-fetch-site")),
        "same-origin fetch origin": same.get("origin"),
        "cross-site fetch origin": cross.get("origin"),
        "cross-site fetch sec-fetch-site": cross.get("sec-fetch-site"),
        "form factors hint": doc.get("sec-ch-ua-form-factors"),
        "mobile hint on subresource": img.get("sec-ch-ua-mobile"),
    }, {
        "document accept": NAV_ACCEPT,
        "document upgrade-insecure-requests": "1",
        "document sec-fetch-dest/mode": ("document", "navigate"),
        "image accept": IMG_ACCEPT,
        "image sec-fetch-*": ("image", "no-cors", "same-origin"),
        "same-origin fetch sec-fetch-*": ("empty", "cors", "same-origin"),
        "same-origin fetch origin": None,
        "cross-site fetch origin": origin,
        "cross-site fetch sec-fetch-site": "cross-site",
        "form factors hint": '"Mobile"',
        "mobile hint on subresource": "?1",
    })
    print("\n=== control (no profile): Firefox's own headers ===")
    server, _, _ = await probe(binary, {})
    doc = first(server, "/")
    control = compare({"document accept is Chrome's": doc.get("accept") == NAV_ACCEPT,
                       "client hints": doc.get("sec-ch-ua")},
                      {"document accept is Chrome's": False, "client hints": None})
    print("\nPASS" if ok and control else "\nFAIL")
    return ok and control


if __name__ == "__main__":
    run_guard(main)
