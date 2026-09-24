"""
Verify the synthetic device sensors (patches/android/android-06-sensors.patch).

A desktop has no accelerometer or gyroscope. With {"device:profile": "pixel10"}
the page must receive a stream that looks like a phone held still-ish:

  * devicemotion / deviceorientation / deviceorientationabsolute at ~60 Hz,
    devicemotion.interval == 16, all events trusted;
  * values rounded as Chromium rounds them: acceleration and Euler angles to
    multiples of 0.1, rotation rate to 0.1 degree measured in radians;
  * beta inside [0, 5] and gamma inside [0, 2] degrees, give or take the
    micro-tremor (sigma 0.15);
  * accelerationIncludingGravity *consistent with that tilt*: gravity is
    (-g cos b sin c, g sin b, g cos b cos c), so for a phone tilted 0-5 degrees
    it sits almost entirely on +z. A fingerprinter can recompute the tilt from
    gravity and compare; a stream where the two disagree is synthetic.
  * noise: acceleration sigma ~0.08 m/s^2, rotation rate sigma ~0.3 deg/s.

The control launch, without the profile, must fire nothing: the host has no
sensors.

Run:
    python tests/patches/android-sensors.py [--binary /path/to/camoufox-bin]
"""

import math
import statistics
from typing import Any, Dict, List

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

COLLECT_MS = 2000
G = 9.80665

PROBE = r"""(ms) => new Promise(resolve => {
  const motion = [], rel = [], abs = [];
  addEventListener('devicemotion', e => motion.push({
    t: performance.now(), trusted: e.isTrusted, interval: e.interval,
    a: [e.acceleration.x, e.acceleration.y, e.acceleration.z],
    g: [e.accelerationIncludingGravity.x, e.accelerationIncludingGravity.y, e.accelerationIncludingGravity.z],
    r: [e.rotationRate.alpha, e.rotationRate.beta, e.rotationRate.gamma],
  }));
  addEventListener('deviceorientation', e => rel.push({
    t: performance.now(), trusted: e.isTrusted, absolute: e.absolute,
    alpha: e.alpha, beta: e.beta, gamma: e.gamma}));
  addEventListener('deviceorientationabsolute', e => abs.push({
    t: performance.now(), trusted: e.isTrusted, absolute: e.absolute,
    alpha: e.alpha, beta: e.beta, gamma: e.gamma}));
  setTimeout(() => resolve({motion, rel, abs}), ms);
})"""


def is_multiple(value: float, step: float) -> bool:
    return abs(value / step - round(value / step)) < 1e-6


def rate(events: List[Dict[str, Any]]) -> float:
    if len(events) < 2:
        return 0.0
    return (len(events) - 1) / ((events[-1]["t"] - events[0]["t"]) / 1000.0)


def analyse(data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    motion, rel, abs_ = data["motion"], data["rel"], data["abs"]
    out: Dict[str, Any] = {
        "devicemotion rate ~60 Hz": rate(motion),
        "deviceorientation rate ~60 Hz": rate(rel),
        "deviceorientationabsolute rate ~60 Hz": rate(abs_),
    }
    if not motion or not rel or not abs_:
        return out
    gyro_step = math.degrees(0.00174532925199432963)
    out.update({
        "all events trusted": all(e["trusted"] for e in motion + rel + abs_),
        "devicemotion.interval": sorted({e["interval"] for e in motion}),
        "deviceorientation.absolute": sorted({e["absolute"] for e in rel}),
        "deviceorientationabsolute.absolute": sorted({e["absolute"] for e in abs_}),
        "acceleration on 0.1 grid": all(is_multiple(v, 0.1) for e in motion for v in e["a"] + e["g"]),
        "rotationRate on 0.1-degree-in-radians grid": all(
            is_multiple(math.radians(v), 0.00174532925199432963) for e in motion for v in e["r"]),
        "orientation on 0.1 grid": all(
            is_multiple(e[k], 0.1) for e in rel + abs_ for k in ("alpha", "beta", "gamma")),
        "mean beta": statistics.fmean(e["beta"] for e in rel),
        "mean gamma": statistics.fmean(e["gamma"] for e in rel),
        "beta tremor sigma": statistics.pstdev(e["beta"] for e in rel),
        "acceleration sigma": statistics.pstdev(v for e in motion for v in e["a"]),
        "rotationRate sigma": statistics.pstdev(v for e in motion for v in e["r"]),
        "|g| ~ 9.81": statistics.fmean(math.sqrt(sum(v * v for v in e["g"])) for e in motion),
        "gravity mostly on +z": statistics.fmean(e["g"][2] for e in motion),
        "gravity y": statistics.fmean(e["g"][1] for e in motion),
        "gravity x": statistics.fmean(e["g"][0] for e in motion),
    })
    # Gravity must agree with the reported tilt: recompute beta from gravity.
    b = math.degrees(math.atan2(out["gravity y"], math.hypot(out["gravity x"], out["gravity mostly on +z"])))
    out["tilt from gravity matches beta"] = abs(b - out["mean beta"])
    out["_gyro_step"] = gyro_step
    return out


EXPECTED = {
    "devicemotion rate ~60 Hz": lambda v: 50 <= v <= 66,
    "deviceorientation rate ~60 Hz": lambda v: 50 <= v <= 66,
    "deviceorientationabsolute rate ~60 Hz": lambda v: 50 <= v <= 66,
    "all events trusted": True,
    "devicemotion.interval": [16],
    "deviceorientation.absolute": [False],
    "deviceorientationabsolute.absolute": [True],
    "acceleration on 0.1 grid": True,
    "rotationRate on 0.1-degree-in-radians grid": True,
    "orientation on 0.1 grid": True,
    "mean beta": lambda v: -0.3 <= v <= 5.3,
    "mean gamma": lambda v: -0.3 <= v <= 2.3,
    "beta tremor sigma": lambda v: 0.08 <= v <= 0.25,
    "acceleration sigma": lambda v: 0.04 <= v <= 0.14,
    "rotationRate sigma": lambda v: 0.2 <= v <= 0.4,
    "|g| ~ 9.81": lambda v: abs(v - G) < 0.15,
    "gravity mostly on +z": lambda v: v > 9.6,
    "tilt from gravity matches beta": lambda v: v < 0.5,
}


async def probe(binary, config):
    with PageServer({"/": ("text/html", "<!doctype html><title>sensors</title>")}) as server:
        async with launch_raw(binary, config) as page:
            await page.goto(server.url("/"))
            return await page.evaluate(PROBE, COLLECT_MS)


async def main(binary) -> bool:
    print(f"\n=== pixel10: {COLLECT_MS} ms of sensor events ===")
    pixel = compare(analyse(await probe(binary, PIXEL10)), EXPECTED)

    print("\n=== control (no profile): the host has no sensors ===")
    data = await probe(binary, {})
    control = compare(
        {k: len(v) for k, v in data.items()},
        {"motion": 0, "rel": 0, "abs": 0},
    )
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
