"""
Verify canvas pixels are exact and reproducible
(patches/android/android-26-canvas-exact.patch; the change is the profile's
prefs).

Chrome adds no noise to canvas readbacks, so neither may the phone profile:

  * fillStyle rgb(10,20,30) reads back as exactly [10, 20, 30, 255];
  * a scene with text, a gradient, arcs and alpha reads back identically
    twice from one canvas, from two canvases, and as the same toDataURL();
  * a worker's OffscreenCanvas draws the solid colours identically;
  * the same scene after a reload hashes the same.

Run:
    python tests/patches/android-canvas-exact.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

SCENE = r"""
function scene(ctx) {
  ctx.fillStyle = 'rgb(10,20,30)'; ctx.fillRect(0, 0, 50, 50);
  const g = ctx.createLinearGradient(0, 0, 200, 0);
  g.addColorStop(0, '#f60'); g.addColorStop(1, 'rgba(0,120,255,0.5)');
  ctx.fillStyle = g; ctx.fillRect(50, 0, 150, 50);
  ctx.beginPath(); ctx.arc(100, 80, 30, 0, Math.PI * 1.7); ctx.strokeStyle = '#3a3'; ctx.lineWidth = 3; ctx.stroke();
  ctx.fillStyle = 'rgba(200,0,100,0.37)'; ctx.font = '18px sans-serif';
  ctx.fillText('Cwm fjord \u{1F600}', 10, 120);
}
"""

WORKER_JS = SCENE + """
const c = new OffscreenCanvas(200, 140); const ctx = c.getContext('2d'); scene(ctx);
postMessage(Array.from(ctx.getImageData(0, 0, 1, 1).data));"""

PROBE = "async () => {" + SCENE + r"""
  const make = () => { const c = document.createElement('canvas'); c.width = 200; c.height = 140;
                       const ctx = c.getContext('2d'); scene(ctx); return [c, ctx]; };
  const [a, actx] = make(), [b, bctx] = make();
  const px = (ctx) => Array.from(ctx.getImageData(0, 0, 200, 140).data);
  const hash = async arr => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',
      new Uint8Array(arr)))).map(x => x.toString(16).padStart(2, '0')).join('');
  const first = px(actx), second = px(actx), other = px(bctx);
  const worker = await new Promise(r => { new Worker('/w.js').onmessage = e => r(e.data); });
  return {
    solid: first.slice(0, 4),
    sameTwice: first.every((v, i) => v === second[i]),
    sameAcrossCanvases: first.every((v, i) => v === other[i]),
    sameDataURL: a.toDataURL() === b.toDataURL(),
    workerSolid: worker,
    hash: await hash(first),
  };
}"""


# The probe reads ImageData, which the isolated world may not do (TypedArray
# data over Xrays is forbidden), so the page defines it and a "mw:" evaluation
# runs it.
PAGE = "<!doctype html><title>exact</title><script>window.probe = " + PROBE + ";</script>"


async def probe(binary, config):
    routes = {"/": ("text/html", PAGE),
              "/w.js": ("text/javascript", WORKER_JS)}
    with PageServer(routes) as server:
        async with launch_raw(binary, dict(config, allowMainWorld=True)) as page:
            await page.goto(server.url("/"))
            first = await page.evaluate("mw:window.probe()")
            await page.reload()
            again = await page.evaluate("mw:window.probe()")
            return first, again


async def main(binary) -> bool:
    print("\n=== pixel10: exact, reproducible pixels ===")
    first, again = await probe(binary, PIXEL10)
    ok = compare({
        "rgb(10,20,30)": first["solid"],
        "same readback twice": first["sameTwice"],
        "same across canvases": first["sameAcrossCanvases"],
        "same toDataURL": first["sameDataURL"],
        "worker rgb(10,20,30)": first["workerSolid"],
        "same after reload": first["hash"] == again["hash"],
    }, {
        "rgb(10,20,30)": [10, 20, 30, 255],
        "same readback twice": True,
        "same across canvases": True,
        "same toDataURL": True,
        "worker rgb(10,20,30)": [10, 20, 30, 255],
        "same after reload": True,
    })
    print("\nPASS" if ok else "\nFAIL")
    return ok


if __name__ == "__main__":
    run_guard(main)
