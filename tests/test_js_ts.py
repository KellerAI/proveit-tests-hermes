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
