#!/usr/bin/env python3
"""Offline Chromium acceptance checks and screenshots for the sample reader."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / ".test-output"
    output.mkdir(exist_ok=True)
    errors, network = [], []
    isolated = tempfile.TemporaryDirectory(prefix="plan-html-offline-")
    standalone = Path(isolated.name) / "plan.html"
    shutil.copyfile(ROOT / "preview.html", standalone)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1512, "height": 1000}, color_scheme="light", reduced_motion="reduce")
        context.route("http://**/*", lambda route: (network.append(route.request.url), route.abort()))
        context.route("https://**/*", lambda route: (network.append(route.request.url), route.abort()))
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("requestfailed", lambda request: errors.append("Failed resource: " + request.url[:150]))
        page.goto(standalone.as_uri())
        page.wait_for_selector('html[data-reader-ready="true"]', timeout=45000, state="attached")
        assert page.locator('.document').count() == 4
        assert page.locator('.hero h1').text_content() == 'Visualização de planos em HTML'
        assert page.locator('.hero-subtitle').count() == 0
        assert page.locator('.mermaid svg').count() == 1, "Mermaid not rendered"
        assert not page.locator('.diagram-error:not([hidden])').count(), "Mermaid failed"
        page.evaluate('Array.from(document.images).forEach(image=>image.loading="eager")')
        page.wait_for_function('Array.from(document.images).filter(image=>image.classList.contains("zoomable")).every(image=>image.complete&&image.naturalWidth>0)')
        assert page.evaluate('Array.from(document.images).filter(image=>image.classList.contains("zoomable")).every(image=>image.complete&&image.naturalWidth>0)'), "A reference image failed"
        assert not errors, errors
        assert not network, network
        page.screenshot(path=str(output / "desktop-light.png"))
        light_svg = page.locator('.mermaid svg').get_attribute('id')
        page.locator('#theme-toggle').click()
        page.wait_for_function('document.documentElement.dataset.theme === "dark"')
        page.wait_for_function('(previous) => document.querySelector(".mermaid svg")?.id !== previous', arg=light_svg)
        assert page.locator('#theme-toggle').get_attribute('aria-checked') == 'true'
        page.screenshot(path=str(output / "desktop-dark.png"))
        page.reload()
        page.wait_for_selector('html[data-reader-ready="true"]', state="attached")
        assert page.locator('html').get_attribute('data-theme') == 'dark', "Theme not persisted"
        page.keyboard.press('Control+k')
        page.locator('#search-input').fill('rastreabilidade')
        assert page.locator('.search-result').count() >= 1
        page.keyboard.press('ArrowDown')
        page.keyboard.press('Enter')
        assert not page.locator('#search-dialog').evaluate('(element)=>element.open')
        assert 'rastreabilidade' in page.url
        page.keyboard.press('Control+k')
        page.locator('#search-input').fill('navegacao')
        assert page.locator('.search-result').count() >= 1, "Accent-insensitive search failed"
        page.keyboard.press('Escape')
        image = page.locator('.prose img.zoomable').first
        image.scroll_into_view_if_needed()
        image.focus()
        page.keyboard.press('Enter')
        assert page.locator('#image-dialog').evaluate('(element)=>element.open')
        page.keyboard.press('Escape')
        page.locator('#focus-toggle').click()
        assert page.locator('#sidebar').is_hidden()
        page.locator('#focus-toggle').click()
        page.locator('.copy-code').first.click()
        page.locator('#toast').wait_for(state='visible')
        assert page.locator('#toast').is_visible()
        # Every local fragment must resolve, including footnotes and cross-file links.
        broken = page.evaluate('Array.from(document.querySelectorAll("a[href^=\\"#\\"]")).map(a=>a.getAttribute("href")).filter(href=>href!=="#"&&!document.getElementById(decodeURIComponent(href.slice(1))))')
        assert not broken, broken
        page.emulate_media(media="print")
        assert page.locator('.topbar').is_hidden()
        page.emulate_media(media="screen")
        page.set_viewport_size({"width":390,"height":844})
        page.evaluate('location.hash="overview"')
        page.wait_for_timeout(150)
        page.locator('#theme-toggle').click()
        page.wait_for_function('document.documentElement.dataset.theme === "light"')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), "Mobile horizontal overflow"
        page.locator('#menu-toggle').click()
        assert page.locator('body').evaluate('element=>element.classList.contains("nav-open")')
        page.locator('.doc-link').nth(1).click()
        assert not page.locator('body').evaluate('element=>element.classList.contains("nav-open")')
        page.evaluate('location.hash="overview"')
        page.wait_for_timeout(150)
        page.locator('#toast').wait_for(state='hidden')
        page.locator('.target-highlight').wait_for(state='detached')
        page.screenshot(path=str(output / "mobile-light.png"))
        assert not errors, errors
        assert not network, network
        print(json.dumps({"browser":"Chromium", "checks":["offline-file", "relocated-html", "source-images", "mermaid", "theme-switch-and-persistence", "global-search", "accent-search", "keyboard-image-zoom", "focus", "code-copy", "internal-links", "print", "mobile-navigation", "mobile-overflow"], "errors":errors, "network_requests":network, "screenshots":str(output)}, indent=2))
        browser.close()
    isolated.cleanup()


if __name__ == '__main__':
    main()
