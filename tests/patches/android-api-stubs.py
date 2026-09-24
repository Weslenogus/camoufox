"""
Verify the Android-only API surface (patches/android/android-04-android-apis.patch).

Chrome on Android exposes APIs desktop browsers do not; their absence alone
says "desktop". With {"device:profile": "pixel10"}:

  * Web NFC: NDEFReader, NDEFMessage, NDEFRecord, NDEFReadingEvent, with the
    right shape -- constructors, onreading/onreadingerror, scan() / write() /
    makeReadOnly() returning promises that reject NotAllowedError (no NFC
    permission on a device nobody is holding), and NDEFRecord/NDEFMessage
    round-tripping their init dictionaries;
  * Contact Picker: navigator.contacts (ContactsManager), getProperties()
    resolving Chrome's five properties, select() rejecting SecurityError
    without user activation (called from the page's own script at load) and
    resolving with it (Juggler, like Chromium, evaluates with a user gesture;
    the picker is dismissed at once); ContactAddress present;
  * window.orientation (0), window.onorientationchange,
    window.ondeviceorientationabsolute.

All of them are secure-context APIs; the control launch must have none of the
Android-only ones.

Run:
    python tests/patches/android-api-stubs.py [--binary /path/to/camoufox-bin]
"""

from helpers import PIXEL10, PageServer, compare, launch_raw, run_guard

PROBE = r"""async () => {
  const out = {};
  for (const name of ['NDEFReader', 'NDEFMessage', 'NDEFRecord', 'NDEFReadingEvent',
                      'ContactsManager', 'ContactAddress'])
    out[name] = name in window;
  out['navigator.contacts'] = 'contacts' in navigator;
  out['window.orientation'] = 'orientation' in window ? window.orientation : 'absent';
  out['onorientationchange'] = 'onorientationchange' in window;
  out['ondeviceorientationabsolute'] = 'ondeviceorientationabsolute' in window;
  if (!out.NDEFReader) return out;

  const reader = new NDEFReader();
  out['reader instanceof EventTarget'] = reader instanceof EventTarget;
  out['reader.onreading'] = reader.onreading;
  const reject = async p => { try { await p; return 'resolved'; } catch (e) { return e.name; } };
  out['scan()'] = await reject(reader.scan());
  out['write()'] = await reject(reader.write('hello'));
  out['makeReadOnly()'] = await reject(reader.makeReadOnly());

  const rec = new NDEFRecord({recordType: 'text', data: 'bonjour', lang: 'fr'});
  out['record.recordType'] = rec.recordType;
  out['record.lang'] = rec.lang;
  out['record.data'] = new TextDecoder().decode(rec.data);
  out['record.mediaType'] = rec.mediaType;
  const msg = new NDEFMessage({records: [{recordType: 'url', data: 'https://example.com/'}]});
  out['message.records'] = msg.records.length;
  out['message.records[0].recordType'] = msg.records[0].recordType;
  try { new NDEFRecord({recordType: ''}); out['empty recordType'] = 'accepted'; }
  catch (e) { out['empty recordType'] = e.name; }
  const ev = new NDEFReadingEvent('reading', {serialNumber: '04:a2', message: {records: []}});
  out['event.serialNumber'] = ev.serialNumber;

  out['contacts.getProperties()'] = await navigator.contacts.getProperties();
  out['contacts.select() with activation'] = await reject(navigator.contacts.select(['name']));
  return out;
}"""

EXPECTED = {
    "NDEFReader": True, "NDEFMessage": True, "NDEFRecord": True, "NDEFReadingEvent": True,
    "ContactsManager": True, "ContactAddress": True,
    "navigator.contacts": True,
    "window.orientation": 0,
    "onorientationchange": True,
    "ondeviceorientationabsolute": True,
    "reader instanceof EventTarget": True,
    "reader.onreading": None,
    "scan()": "NotAllowedError",
    "write()": "NotAllowedError",
    "makeReadOnly()": "NotAllowedError",
    "record.recordType": "text",
    "record.lang": "fr",
    "record.data": "bonjour",
    "record.mediaType": None,
    "message.records": 1,
    "message.records[0].recordType": "url",
    "empty recordType": "TypeError",
    "event.serialNumber": "04:a2",
    "contacts.getProperties()": ["address", "email", "icon", "name", "tel"],
    "contacts.select() with activation": "resolved",
    "contacts.select() without activation": "SecurityError",
}

CONTROL = {
    "NDEFReader": False, "NDEFMessage": False, "NDEFRecord": False,
    "NDEFReadingEvent": False, "ContactsManager": False, "ContactAddress": False,
    "navigator.contacts": False, "window.orientation": "absent",
    "onorientationchange": False,
    # Firefox desktop already has this one; Chrome desktop does too.
    "ondeviceorientationabsolute": True,
}


# Runs at load, before anything could give the page user activation.
PAGE = """<!doctype html><title>stubs</title><script>
window.selectWithoutGesture = navigator.contacts
  ? navigator.contacts.select(['name']).then(() => 'resolved', e => e.name)
  : Promise.resolve('absent');
</script>"""


async def probe(binary, config):
    with PageServer({"/": ("text/html", PAGE)}) as server:
        # allowMainWorld only unlocks the guard's own "mw:" read of the result.
        async with launch_raw(binary, dict(config, allowMainWorld=True)) as page:
            await page.goto(server.url("/"))
            out = await page.evaluate(PROBE)
            if out.get("navigator.contacts"):
                out["contacts.select() without activation"] = await page.evaluate(
                    "mw:window.selectWithoutGesture")
            return out


async def main(binary) -> bool:
    print("\n=== pixel10 ===")
    pixel = compare(await probe(binary, PIXEL10), EXPECTED)
    print("\n=== control (no profile) ===")
    control = compare(await probe(binary, {}), CONTROL)
    print("\nPASS" if pixel and control else "\nFAIL")
    return pixel and control


if __name__ == "__main__":
    run_guard(main)
