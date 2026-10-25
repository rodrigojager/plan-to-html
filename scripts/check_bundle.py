#!/usr/bin/env python3
"""Standalone packaging acceptance: custom assets, modules, relocation, and offline behavior."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
def png_chunk(kind,payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)


PNG = (b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
       +png_chunk(b'IDAT',zlib.compress(b'\x00\x30\x80\x20'))+png_chunk(b'IEND',b''))


def bmp():
    # Two pixels at 2x density retain a nonzero intrinsic CSS width.
    pixels = (b'\x20\x80\x30'*2+b'\x00\x00')*2
    return b'BM' + struct.pack('<IHHI',70,0,0,54) + struct.pack('<IiiHHIIiiII',40,2,2,1,24,0,16,2835,2835,0,0) + pixels


class BundleChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plan-html-package-')
        self.folder = Path(self.temp.name)
        self.site = self.folder/'site'
        self.site.mkdir()
        self.output = self.folder/'final.html'

    def tearDown(self):
        self.temp.cleanup()

    def write(self,path,content):
        target = self.site/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding='utf-8')

    def run_pack(self,*options,succeeds=True,output=None):
        result = subprocess.run([sys.executable,str(ROOT/'scripts'/'bundle_html.py'),str(self.site/'index.html'),
                                 '--output',str(output or self.output),*options],capture_output=True,text=True,encoding='utf-8')
        if succeeds:
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode,0)
        return result.stderr

    def fixture(self):
        (self.site/'pixel.png').write_bytes(PNG)
        (self.site/'pixel.bmp').write_bytes(bmp())
        self.write('graphic.svg','<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><image href="pixel.png" width="20" height="20"/></svg>')
        self.write('css/nested/layout.css','#import-marker {border-top:7px solid #123456;background-image:url("../../pixel.png")}')
        self.write('css/main.css','''@import "./nested/layout.css" screen;
body{font-family:system-ui}.animated{animation:pulse 1s infinite alternate}@keyframes pulse{to{opacity:.6}}
#picture{background-image:image-set("../pixel.png" 1x,url("../pixel.bmp") 2x)}
''')
        self.write('css/module.css','#module-marker {color:rgb(25,95,70);background-image:url("../pixel.png")}')
        self.write('scripts/classic.js','window.execution.push("classic"); document.querySelector("#ready").textContent="loaded"; window.literal="</script>";')
        self.write('scripts/lib/step.mjs','export const initial = 7;')
        self.write('scripts/lib/lazy.mjs','export const extra = 5;')
        self.write('scripts/main.mjs','''import {initial} from './lib/step.mjs';
import image from '../pixel.png';
import '../css/module.css';
const lazy = await import('./lib/lazy.mjs');
window.execution.push('module');
document.querySelector('#action').addEventListener('click',()=>{
 document.querySelector('#result').textContent=String(initial+lazy.extra);
 document.querySelector('#module-marker').classList.add('animated');
});
document.querySelector('#imported-image').src=image;
document.documentElement.dataset.moduleReady='yes';
''')
        self.write('index.html','''<!doctype html><html><head><meta charset="utf-8">
<script>window.execution=['inline-head'];</script>
<link rel="stylesheet" href="css/main.css" media="screen">
<script src="scripts/classic.js" defer></script>
<script type="module" src="scripts/main.mjs"></script>
<style>#inline-style{background-image:url('pixel.bmp')}</style>
</head><body><h1>Custom interaction</h1>
<div id="ready"></div><div id="import-marker">Imported CSS</div><div id="module-marker">Module CSS</div>
<button id="action">Calculate</button><output id="result"></output>
<div id="inline-style" style="border-image-source:url('pixel.png')">Inline style</div><div id="picture">Image set</div>
<img id="svg" src="graphic.svg" alt="SVG with nested image"><img id="bmp" src="pixel.bmp" alt="BMP">
<img id="responsive" src="pixel.png" srcset="pixel.png 1x, pixel.bmp 2x" alt="Responsive image">
<picture><source srcset="pixel.png 1x, pixel.bmp 2x"><img src="pixel.png" alt="Picture"></picture>
<img id="imported-image" alt="Imported image"><img src="/pixel.png" alt="Root path">
<a href="https://example.test/">Ordinary hyperlink</a>
<script>window.execution.push('body-tail');</script></body></html>''')

    def test_custom_page_relocated_without_sources_or_network(self):
        from playwright.sync_api import sync_playwright
        self.fixture()
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.site.rglob('*') if p.is_file()}
        report = self.run_pack()
        self.assertTrue(report['self_contained_static_resources'])
        self.assertGreaterEqual(report['embedded_files'],10)
        self.assertEqual(report['external_resources'],[])
        after = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.site.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        first = self.output.read_bytes()
        self.run_pack()
        self.assertEqual(first,self.output.read_bytes())
        isolated = self.folder/'isolated'
        isolated.mkdir()
        final = isolated/'only-file.html'
        shutil.copyfile(self.output,final)
        self.site.rename(self.folder/'sources-unavailable')
        requests,errors = [],[]
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            context.route('http://**/*',lambda route:(requests.append(route.request.url),route.abort()))
            context.route('https://**/*',lambda route:(requests.append(route.request.url),route.abort()))
            page = context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('requestfailed',lambda request:errors.append('Failed resource: '+request.url[:150]))
            page.goto(final.as_uri())
            page.wait_for_function('document.documentElement.dataset.moduleReady === "yes"')
            self.assertEqual(page.locator('#ready').inner_text(),'loaded')
            self.assertEqual(page.evaluate('window.execution'),['inline-head','body-tail','classic','module'])
            self.assertEqual(page.evaluate('window.literal'),'</script>')
            page.locator('#action').click()
            self.assertEqual(page.locator('#result').inner_text(),'12')
            self.assertEqual(page.locator('#import-marker').evaluate('e=>getComputedStyle(e).borderTopWidth'),'7px')
            self.assertEqual(page.locator('#module-marker').evaluate('e=>getComputedStyle(e).color'),'rgb(25, 95, 70)')
            self.assertEqual(page.locator('#module-marker').evaluate('e=>getComputedStyle(e).animationName'),'pulse')
            page.wait_for_function('Array.from(document.images).every(image=>image.complete&&image.naturalWidth>0)')
            self.assertTrue(page.evaluate('Array.from(document.images).every(image=>image.src.startsWith("data:"))'))
            self.assertEqual(requests,[])
            self.assertEqual(errors,[])
            browser.close()

    def test_missing_and_remote_resources_do_not_replace_deliverable(self):
        self.output.write_text('existing deliverable',encoding='utf-8')
        self.write('index.html','<img src="missing.bmp">')
        self.assertIn('Missing resource',self.run_pack(succeeds=False))
        self.assertEqual(self.output.read_text(),'existing deliverable')
        self.write('index.html','<img src="https://example.test/image.png">')
        self.assertIn('External resource',self.run_pack(succeeds=False))
        self.assertEqual(self.output.read_text(),'existing deliverable')
        report = self.run_pack('--allow-external')
        self.assertFalse(report['self_contained_static_resources'])
        self.assertEqual(report['external_resources'],['https://example.test/image.png'])

    def test_font_embedded_and_srcset_with_existing_data_uri(self):
        font = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf'
        if not font.exists():
            self.skipTest('A local test font is unavailable')
        shutil.copyfile(font,self.site/'sample.ttf')
        (self.site/'pixel.png').write_bytes(PNG)
        existing = 'data:image/png;base64,'+base64.b64encode(PNG).decode()
        self.write('index.html',f'''<style>@font-face{{font-family:Fixture;src:url("sample.ttf")}}body{{font-family:Fixture}}</style>
<p>Font sample</p><img src="pixel.png" srcset="{existing} 1x, pixel.png 2x">''')
        report = self.run_pack()
        self.assertEqual(report['embedded_files'],2)
        page = self.output.read_text(encoding='utf-8')
        self.assertTrue('data:font/' in page,'Embedded font MIME missing')
        self.assertTrue(existing in page,'Existing data URI was changed')
        self.assertFalse('src="pixel.png"' in page,'A local image reference remains')

    def test_css_import_cycle_is_reported(self):
        self.write('index.html','<link rel="stylesheet" href="a.css">')
        self.write('a.css','@import "b.css";')
        self.write('b.css','@import "a.css";')
        self.assertIn('Circular resource import',self.run_pack(succeeds=False))

    def test_reader_extension_files_receive_ready_and_theme_events(self):
        from playwright.sync_api import sync_playwright
        self.write('PLAN.md','# Plano de interação\n\n## Objetivo\n\nVerificar os recursos adicionais.\n')
        self.write('custom.css','.hero h1 {letter-spacing:0.01em}')
        self.write('custom.js','''window.customThemes=[];
document.addEventListener('planhtml:ready',()=>document.documentElement.dataset.customReady='yes');
document.addEventListener('planhtml:theme',event=>window.customThemes.push(event.detail.theme));''')
        self.write('custom.mjs',"document.addEventListener('planhtml:ready',()=>document.documentElement.dataset.customModuleReady='yes');")
        build = subprocess.run([sys.executable,str(ROOT/'scripts'/'plan_html.py'),'build',str(self.site/'PLAN.md'),
                                '--output',str(self.site/'index.html'),'--extra-css',str(self.site/'custom.css'),
                                '--extra-js',str(self.site/'custom.js'),'--extra-module',str(self.site/'custom.mjs')],
                               capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(build.returncode,0,build.stderr)
        self.run_pack()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.output.as_uri())
            page.wait_for_function('document.documentElement.dataset.customReady === "yes" && document.documentElement.dataset.customModuleReady === "yes"')
            self.assertGreater(float(page.locator('.hero h1').evaluate('e=>parseFloat(getComputedStyle(e).letterSpacing)')),0)
            page.locator('#theme-toggle').click()
            self.assertEqual(page.evaluate('window.customThemes.length'),1)
            self.assertEqual(page.evaluate('window.customThemes[0]'),page.locator('html').get_attribute('data-theme'))
            browser.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
