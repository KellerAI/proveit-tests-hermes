from pathlib import Path

from proveit_tests.detectors.js_ts import detect_js_ts_diff, detect_js_ts_source

CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def test_js_skip():
    src = (CORPUS / "cheats/js_skip.test.js").read_text()
    f = detect_js_ts_source(src, path="x.test.js")
    assert any(x.kind == "js-skip" for x in f)


def test_js_expect_true():
    src = (CORPUS / "cheats/js_expect_true.test.js").read_text()
    f = detect_js_ts_source(src, path="x.test.js")
    assert any(x.kind == "js-expect-true" for x in f)


def test_js_deleted_test():
    old = "test('a', () => { expect(1).toBe(1); });\ntest('b', () => { expect(2).toBe(2); });\n"
    new = "test('a', () => { expect(1).toBe(1); });\n"
    f = detect_js_ts_diff(old, new, path="x.test.js")
    assert any(x.kind == "js-deleted-test" for x in f)


def test_js_removed_expect():
    old = "test('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    new = "test('a', () => { expect(1).toBe(1); });\n"
    f = detect_js_ts_diff(old, new, path="x.test.js")
    assert any(x.kind == "js-removed-expect" for x in f)


def test_js_literal_rewrite():
    old = "test('a', () => { expect(total).toBe(10); });\n"
    new = "test('a', () => { expect(total).toBe(9); });\n"
    f = detect_js_ts_diff(old, new, path="x.test.js")
    assert any(x.kind == "js-expected-literal-rewrite" for x in f)


# --- Net-new semantics (Andrej breaker P0, 2026-11-05) ----------------------

_JS_OLD = "it.skip('legacy', () => { expect(1).toBe(1); });\ntest('b', () => { expect(2).toBe(2); });\n"


def test_js_identical_with_preexisting_skip_not_flagged():
    assert detect_js_ts_diff(_JS_OLD, _JS_OLD, path="x.test.js") == []


def test_js_newly_added_only_is_flagged():
    new = _JS_OLD.replace("test('b'", "test.only('b'")
    kinds = [f.kind for f in detect_js_ts_diff(_JS_OLD, new, path="x.test.js")]
    assert kinds == ["js-only"]


def test_js_preexisting_empty_catch_not_flagged_new_one_is():
    old = "test('a', () => { try { f(); } catch (e) {} expect(1).toBe(1); });\n"
    assert detect_js_ts_diff(old, old, path="x.test.js") == []
    new = old + "test('c', () => { try { g(); } catch {} expect(3).toBe(3); });\n"
    assert [f.kind for f in detect_js_ts_diff(old, new, path="x.test.js")] == ["js-empty-catch"]
