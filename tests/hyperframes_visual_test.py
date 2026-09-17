"""Visual regression tests for the long-form thumbnail HyperFrames compositions.

Renders each composition's settled end-frame in a real browser via Playwright
and diffs it against a stored baseline PNG, catching unintended layout/style
changes (e.g. a title card's box chrome coming back, a ribbon shifting, text
overflowing) before they reach a rendered thumbnail.

Requires the optional `playwright` package and its Chromium browser:
    pip install playwright
    playwright install chromium

To (re)create baselines after an intentional composition change:
    UPDATE_HYPERFRAMES_BASELINES=1 python -m pytest tests/hyperframes_visual_test.py
"""

import os
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
HYPERFRAMES_ROOT = REPO_ROOT / "long_form" / "hyperframes"
BASELINE_DIR = Path(__file__).resolve().parent / "hyperframes_baselines"

COMPOSITIONS = [
    "thumbnail-title-side",
    "thumbnail-title-stacked",
    "thumbnail-title-diagonal",
]

MAX_DIFF_RATIO = 0.01  # allow up to 1% of pixels to differ before failing


def _render_composition(browser, composition: str) -> bytes:
    comp_dir = HYPERFRAMES_ROOT / composition
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    try:
        page.goto((comp_dir / "index.html").as_uri())
        page.wait_for_function("() => Boolean(window.__timelines && window.__timelines['main'])")
        # Jump to the settled end of the intro animation, matching what the
        # ffmpeg frame-extraction step in the real render pipeline captures.
        page.evaluate("window.__timelines['main'].progress(1).pause()")
        page.wait_for_timeout(200)
        return page.screenshot(omit_background=True)
    finally:
        page.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.mark.parametrize("composition", COMPOSITIONS)
def test_composition_visual_regression(browser, composition):
    screenshot_bytes = _render_composition(browser, composition)
    baseline_path = BASELINE_DIR / f"{composition}.png"

    if os.environ.get("UPDATE_HYPERFRAMES_BASELINES"):
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(screenshot_bytes)
        pytest.skip(f"Updated baseline for {composition}")

    if not baseline_path.exists():
        pytest.fail(
            f"No baseline for '{composition}' at {baseline_path}. "
            "Run with UPDATE_HYPERFRAMES_BASELINES=1 to create one after "
            "confirming the current render looks correct."
        )

    current = Image.open(BytesIO(screenshot_bytes)).convert("RGBA")
    baseline = Image.open(baseline_path).convert("RGBA")
    assert current.size == baseline.size, (
        f"'{composition}' rendered size changed: {baseline.size} -> {current.size}"
    )

    diff = np.asarray(ImageChops.difference(current, baseline))
    diff_ratio = float(np.mean(diff.any(axis=-1)))
    assert diff_ratio <= MAX_DIFF_RATIO, (
        f"'{composition}' visual regression: {diff_ratio:.2%} of pixels changed "
        f"(threshold {MAX_DIFF_RATIO:.2%}). If this change is intentional, "
        "rerun with UPDATE_HYPERFRAMES_BASELINES=1 to accept the new baseline."
    )
