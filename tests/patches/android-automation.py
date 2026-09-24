"""
Verify no automation markers reach the page on the Android profile
(patches/android/android-15-automation.patch).

With {"device:profile": "pixel10"}, and driven by Playwright the whole time:

  * navigator.webdriver is false -- defined on Navigator.prototype, as in every
    real Chrome. (Deleting it outright would itself be a marker: the member has
    existed in every browser since 2019.)
  * none of the globals Selenium, ChromeDriver, PhantomJS, Nightmare, Puppeteer,
    Playwright or CDP leave behind exist on window or document;
  * document.documentElement carries no webdriver/selenium/driver attribute;
  * Error().stack, captured by page code that automation *caused* to run
    (page.evaluate calling into the page, page.click on a listener), holds no
    frame from the automation side -- no juggler, playwright, puppeteer,
    __pw, "debugger eval code", chrome:// or resource:// URLs.

Run:
    python tests/patches/android-automation.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

GLOBALS = [
    "_Selenium_IDE_Recorder", "_selenium", "calledSelenium", "__selenium_unwrapped",
    "__selenium_evaluate", "__webdriver_evaluate", "__driver_evaluate",
    "__webdriver_script_function", "__webdriver_script_func", "__webdriver_script_fn",
    "__fxdriver_evaluate", "__driver_unwrapped", "__webdriver_unwrapped",
    "__fxdriver_unwrapped", "__lastWatirAlert", "__lastWatirConfirm", "__lastWatirPrompt",
    "$cdc_asdjflasutopfhvcZLmcfl_", "$chrome_asyncScriptInfo", "cdc_adoQpoasnfa76pfcZLmcfl_Array",
    "cdc_adoQpoasnfa76pfcZLmcfl_Promise", "cdc_adoQpoasnfa76pfcZLmcfl_Symbol",
    "callPhantom", "_phantom", "phantom", "__nightmare", "domAutomation",
    "domAutomationController", "webdriver", "__playwright", "__pwInitScripts",
    "__playwright__binding__", "__pw_manual", "playwright", "__puppeteer_evaluation_script__",
    "puppeteer", "__cdp_binding", "cdp",
]

PAGE = """<!doctype html><title>automation</title>
<button id=b>b</button>
<script>
  window.stacks = [];
  window.pageFunction = () => { stacks.push(new Error().stack); return 1; };
  b.addEventListener('click', () => stacks.push(new Error().stack));
</script>"""

PROBE = r"""(globals) => ({
  webdriver: navigator.webdriver,
  webdriverOnPrototype: Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver') !== undefined,
  leakedGlobals: globals.filter(g => g in window || g in document),
  cdcDocumentKeys: Object.keys(document).filter(k => /cdc_|\$chrome_/.test(k)),
  rootAttributes: ['webdriver', 'selenium', 'driver'].filter(a =>
      document.documentElement.hasAttribute(a)),
})"""

MARKERS = ["juggler", "playwright", "puppeteer", "__pw", "debugger eval code",
           "chrome://", "resource://", "pptr:", "__selenium", "webdriver"]


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            await page.evaluate("mw:window.pageFunction()")
            await page.evaluate("document.getElementById('b').click()")
            await page.click("#b")
            data = await page.evaluate(PROBE, GLOBALS)
            data["stacks"] = await page.evaluate("mw:window.stacks")
            return data


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    # allowMainWorld only unlocks the guard's own "mw:" reads of page state.
    data = await probe(binary, dict(PIXEL10, allowMainWorld=True))
    stacks = data.pop("stacks")
    for s in stacks:
        print("    [info] stack: " + " | ".join(s.strip().splitlines()))
    marked = [m for m in MARKERS for s in stacks if m in s.lower()]
    ok = compare(dict(data, stacksCaptured=len(stacks), stackMarkers=marked), {
        "webdriver": False, "webdriverOnPrototype": True, "leakedGlobals": [],
        "cdcDocumentKeys": [], "rootAttributes": [],
        "stacksCaptured": lambda n: n >= 2, "stackMarkers": [],
    })
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
