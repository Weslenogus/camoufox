"""
Verify the Battery Status API on the Android profile
(patches/android/android-10-battery.patch).

Firefox keeps navigator.getBattery() for its own UI; Chrome on Android exposes
it to every secure page. With {"device:profile": "pixel10"}:

    level 0.78    charging false    chargingTime Infinity    dischargingTime 14400

and BatteryManager is a visible interface. Without the profile the API stays
where Firefox keeps it: invisible to content.

Run:
    python tests/patches/android-battery.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  if (!('getBattery' in navigator)) return {exposed: false, iface: 'BatteryManager' in window};
  const b = await navigator.getBattery();
  return {
    exposed: true, iface: 'BatteryManager' in window,
    sameObject: b === await navigator.getBattery(),
    level: b.level, charging: b.charging,
    chargingTime: String(b.chargingTime), dischargingTime: b.dischargingTime,
  };
}"""


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>battery</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE)


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    pixel = compare(await probe(binary, PIXEL10), {
        "exposed": True, "iface": True, "sameObject": True, "level": 0.78,
        "charging": False, "chargingTime": "Infinity", "dischargingTime": 14400,
    })
    print("\n=== control (no profile): content cannot see the battery ===")
    control = compare(await probe(binary, {}), {"exposed": False, "iface": False})
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
