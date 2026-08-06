"""The viewer's </body> injectors must splice at the DOCUMENT's closing tag.

2026-07-17 incident: both injectors used ``.replace("</body>", ..., 1)`` — the
FIRST match. A self-contained artifact inlines mermaid.min.js (~3.5 MB), whose
source carries the literal bytes ``</body>`` inside a JS string (DOMPurify's
``'<html ...><head></head><body>'+x+"</body></html>"``). So the injected
``<script>…</script>`` landed INSIDE the vendored <script> block; its
``</script>`` closed that block early and the remaining ~3.3 MB of JS was
reparsed as markup → a ~482,000 px page that crashed Chrome's screenshotter.

Every mermaid artifact was broken from the injector shipping (2026-07-12) until
2026-07-17 and NOTHING went red: bh_build returned ok/self_contained/sha256, the
index listed it, and the file itself (file://, uninjected) rendered fine. Only
the served copy was broken, and only a real screenshot revealed it.

Negative control matters here: assert the payload lands AFTER the vendored
script, not merely that it is "present" — the buggy version also had it present.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from serve import _inject_before_body_end  # noqa: E402

# The real shape: a vendored <script> whose JS *string* contains "</body>".
VENDOR_TRAP = (
    "<!DOCTYPE html><html><head>"
    '<script>var t = \'<html xmlns="x"><head></head><body>\'+De+"</body></html>";'
    "var tail = 'AAAA';</script>"
    "</head><body><pre class='mermaid'>graph TD</pre></body></html>"
)
PAYLOAD = "<script data-x>(function(){})();</script>"


def _check(doc, payload):
    out = _inject_before_body_end(doc, payload)
    vendor_end = out.index("</script>")
    inject_at = out.index(payload)
    doc_body_end = out.rindex("</body>")
    return out, vendor_end, inject_at, doc_body_end


def test_payload_lands_after_vendor_script_not_inside_it():
    out, vendor_end, inject_at, _ = _check(VENDOR_TRAP, PAYLOAD)
    # THE bug: buggy version put the payload before the vendored script ended.
    assert inject_at > vendor_end, (
        "payload spliced INSIDE the vendored <script> — its </script> will close "
        "that block early and the rest of the JS becomes markup"
    )


def test_payload_immediately_precedes_document_body_end():
    out, _, inject_at, doc_body_end = _check(VENDOR_TRAP, PAYLOAD)
    assert inject_at + len(PAYLOAD) == doc_body_end


def test_vendored_script_survives_intact():
    out, _, _, _ = _check(VENDOR_TRAP, PAYLOAD)
    # The JS string must still read exactly as authored.
    assert '\'<html xmlns="x"><head></head><body>\'+De+"</body></html>"' in out
    # Script open/close must stay balanced (the 482k-px symptom was imbalance).
    assert out.count("<script") == out.count("</script>")


def test_bytes_and_str_both_supported():
    b_out = _inject_before_body_end(VENDOR_TRAP.encode(), PAYLOAD.encode())
    assert isinstance(b_out, bytes)
    assert b_out.decode() == _inject_before_body_end(VENDOR_TRAP, PAYLOAD)


def test_no_closing_tag_returns_input_unchanged():
    frag = "<div>no body tag</div>"
    assert _inject_before_body_end(frag, PAYLOAD) == frag


def test_negative_control_first_match_replace_would_fail():
    """Prove this ruler can go red: the OLD implementation must break these."""
    buggy = VENDOR_TRAP.replace("</body>", PAYLOAD + "</body>", 1)
    vendor_end = buggy.index("</script>")
    assert buggy.index(PAYLOAD) < vendor_end, (
        "the old first-match splice should land inside the vendored script — if "
        "this assert fails the fixture no longer reproduces the 2026-07-17 bug "
        "and the tests above are measuring nothing"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n  → {len(fns) - fails}/{len(fns)} 通過")
    sys.exit(1 if fails else 0)
