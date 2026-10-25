#!/usr/bin/env python3
"""Append distinct material/interaction themes, preserving the previous collection."""
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def resources():
    folder = ROOT / 'themes/resources'
    folder.mkdir(exist_ok=True)
    rng = random.Random(4321)
    fibers = ''.join(f'<path d="M{x} {y}q{rng.randrange(20,80)} {rng.randrange(-3,4)} {rng.randrange(90,210)} 0"/>' for x,y in [(rng.randrange(-160,500),rng.randrange(500)) for _ in range(170)])
    (folder/'papyrus-fibers.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"><g fill="none" stroke="#71501f" stroke-opacity=".055" stroke-width="1">'+fibers+'</g></svg>')
    (folder/'grain.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".75" numOctaves="3" seed="12" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="100%" height="100%" opacity=".09" filter="url(#grain)"/></svg>')
    (folder/'sketch-frame.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 300" preserveAspectRatio="none"><g fill="none" stroke="#000" stroke-width="1.6"><path d="M8 7L240 4 520 8 994 5 996 151 992 294 750 297 470 292 5 296 8 130Z"/><path d="M4 10L340 7 660 10 997 8M10 2L5 180 12 297M998 5L990 195 995 298M6 291L320 299 700 294 996 290" opacity=".45"/></g></svg>')
    (folder/'deco-frame.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 300" preserveAspectRatio="none"><g fill="none" stroke="#000" stroke-width="1"><path d="M15 2H985V15H998V285H985V298H15V285H2V15H15Z"/><path d="M22 9H978V22H991V278H978V291H22V278H9V22H22Z"/><path d="M2 28L28 2M972 2L998 28M998 272L972 298M28 298L2 272"/></g></svg>')
    (folder/'brush.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 30" preserveAspectRatio="none"><path d="M5 13L160 5 350 8 560 2 790 7 993 5 999 21 760 26 530 23 350 29 140 24 0 27Z"/></svg>')


def main():
    path = HERE / 'catalog.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    profiles = []
    def add(id, name, note, fonts, appearance, light, dark, effects=None, animated=False):
        profiles.append(dict(id=id,name=name,note=note,reference='expressive-materials',collection='expressive',fonts=fonts,appearance=appearance,light=light.split(),dark=dark.split(),effects=effects or {},animated=animated))
    add('neon-laser', 'Neon / Laser', 'Grade, contornos luminosos, laser na seleção e hover iluminado.', ['rajdhani'], {
        'font-heading':'"Plan Rajdhani", sans-serif','hero-weight':'700','heading-weight':'700','hero-case':'uppercase','hero-tracking':'.015em','heading-tracking':'.02em','hero-scale':'1.12',
        'radius':'2px','radius-md':'2px','radius-control':'0px','radius-sm':'1px','radius-media':'2px','panel-border-color':'var(--accent)','panel-edge-mask':'url("resources/deco-frame.svg")','panel-edge-opacity':'.18',
        'selected-marker-opacity':'1','selected-marker-shadow':'0 0 12px var(--accent)','selected-border':'var(--accent)','selected-sheen':'linear-gradient(105deg, transparent 35%, var(--accent) 50%,transparent 65%)','selected-sheen-opacity':'1','selected-sheen-inset':'auto 0 0','selected-sheen-height':'2px','selected-animation':'reader-laser 3.8s linear infinite',
        'hover-transform':'translateY(-2px)','hover-border':'var(--accent)','hover-shadow':'0 0 0 1px var(--accent), 0 0 18px color-mix(in srgb,var(--accent) 24%,transparent)','hover-bg':'var(--accent-soft)','hero-ornament':'linear-gradient(90deg,var(--accent),#ec42cf,transparent)','hero-ornament-height':'2px','hero-ornament-space':'13px',
        'page-texture':'linear-gradient(90deg, color-mix(in srgb,var(--accent) 5%,transparent) 1px,transparent 1px),linear-gradient(color-mix(in srgb,var(--accent) 5%,transparent) 1px,transparent 1px)','page-texture-size':'36px 36px','small-label-font':'var(--mono)'},
        '#eef8fc #faffff #dfedf3 #102b40 #395765 #456271 #aecbd6 #005b78 #d7eef5 #003d52 #e5f0f4',
        '#050812 #0c1322 #14263a #e5fcff #adc8d5 #a0bacb #25455c #56e8ff #173849 #aeffff #08101c',
        {'light':{'panel-shadow':'0 0 0 1px #005b7810, inset 0 0 22px #35dfff08','hero-shadow':'none'},'dark':{'panel-shadow':'0 0 0 1px #56e8ff18, inset 0 0 26px #19bfff09','hero-shadow':'0 0 28px #2ee9ff44, 2px 0 #e54dc829'}}, True)
    add('manuscrito','Manuscrito','Caligrafia, papel pautado, bordas desenhadas e marcador estático.',['caveat','kalam'],{
        'font-heading':'"Plan Caveat", cursive','font-reading':'"Plan Kalam", cursive','hero-weight':'700','hero-tracking':'-.025em','heading-weight':'700','heading-tracking':'0','hero-scale':'1.1','radius':'9px 3px 12px 5px','radius-md':'3px 8px 5px 9px','radius-control':'4px 8px 3px 7px','radius-sm':'3px','radius-media':'6px',
        'panel-edge-mask':'url("resources/sketch-frame.svg")','panel-edge-opacity':'.55','panel-border-width':'0px','document-border':'1px solid var(--line)','document-top-border':'1px solid var(--line)','document-padding':'28px 26px','document-padding-mobile':'24px 15px','document-radius':'4px 8px 5px 10px','document-shadow':'3px 4px 0 color-mix(in srgb,var(--line) 40%,transparent)',
        'hero-ornament':'var(--accent)','hero-ornament-mask':'url("resources/brush.svg")','hero-ornament-height':'5px','hero-ornament-space':'10px','selected-radius':'5px 12px 3px 8px','selected-transform':'rotate(-.45deg)','selected-border':'transparent','hover-bg':'var(--accent-soft)','hover-border':'var(--accent)','duration':'0ms','scroll-behavior':'auto'},
        '#f6f1e7 #fffdf6 #eee9dc #302d25 #605948 #6b6250 #d5cbb5 #654916 #ece1c8 #49340f #f0ebdd',
        '#211f19 #2d2a22 #383428 #f3edde #c5bca4 #baaf95 #55503d #e8c788 #493d26 #ffe2ad #27241c',
        {'light':{'document-bg':'repeating-linear-gradient(transparent 0 29px,#336aa413 29px 30px),linear-gradient(90deg,transparent 17px,#be47371d 17px 18px,transparent 18px),var(--surface)'},'dark':{'document-bg':'repeating-linear-gradient(transparent 0 29px,#b8d3fa0d 29px 30px),linear-gradient(90deg,transparent 17px,#e89b7222 17px 18px,transparent 18px),var(--surface)'}})
    add('crayon','Crayon','Traço de giz de cera, textura de papel, cores e hover rabiscado.',['kalam'],{
        'font-heading':'"Plan Kalam", cursive','hero-weight':'700','heading-weight':'700','hero-tracking':'-.03em','heading-tracking':'-.02em','radius':'16px 5px 20px 7px','radius-md':'6px 16px 7px 12px','radius-control':'8px 3px 10px 4px','radius-sm':'4px 7px 3px 8px','radius-media':'8px',
        'panel-edge-mask':'url("resources/sketch-frame.svg")','panel-edge-opacity':'.85','panel-border-width':'0px','panel-overlay':'url("resources/grain.svg")','panel-overlay-size':'180px 180px','hero-ornament':'linear-gradient(90deg,#dfb142 0 32%,#d25686 32% 67%,#477ea7 67%)','hero-ornament-height':'10px','hero-ornament-space':'15px','hero-ornament-mask':'url("resources/brush.svg")',
        'selected-radius':'13px 4px 10px 3px','selected-transform':'rotate(-.7deg)','selected-border':'var(--accent)','selected-sheen':'linear-gradient(90deg,transparent,var(--accent-soft))','selected-sheen-opacity':'.7','selected-animation':'reader-marker .32s ease-out 1','hover-animation':'reader-chalk .28s ease-out 1','hover-bg':'var(--accent-soft)','hover-border':'var(--accent)','hover-shadow':'2px 3px 0 var(--line)','duration':'180ms'},
        '#faf5e8 #fffcf4 #eee9da #302b29 #60574b #6a5d4d #d6c6a6 #285d79 #e0edf1 #17435c #eee9dc',
        '#24201b #302b23 #40382c #f6edde #d1c0a7 #c3b296 #61513a #9ed7e9 #34443f #c5efff #2b261e',animated=True)
    add('papiro','Papiro','Fibras, bordas gastas, folhas em relevo e títulos de manuscrito antigo.',['cinzel','im-fell-english'],{
        'font-heading':'"Plan Cinzel", Georgia, serif','font-reading':'"Plan Fell", Georgia, serif','heading-weight':'600','hero-weight':'600','heading-tracking':'.025em','hero-tracking':'.015em','hero-scale':'.97','radius':'2px','radius-md':'1px','radius-control':'1px','radius-sm':'0px','radius-media':'2px',
        'page-texture':'url("resources/papyrus-fibers.svg")','page-texture-size':'500px 500px','panel-overlay':'url("resources/papyrus-fibers.svg")','panel-overlay-size':'500px 500px','panel-border-style':'double','panel-border-width':'3px','document-border':'1px solid var(--line)','document-top-border':'1px solid var(--line)','document-padding':'32px 28px','document-padding-mobile':'25px 17px','document-radius':'2px 10px 3px 7px',
        'document-heading-rule':'3px double var(--line)','document-heading-padding':'17px','selected-marker-opacity':'1','selected-border':'var(--accent)','hover-bg':'var(--accent-soft)','hover-border':'var(--accent)','duration':'0ms','scroll-behavior':'auto'},
        '#e8d7b0 #f2e5c7 #dfcda3 #372a18 #635033 #695538 #c5aa76 #704315 #e6d1a5 #4f2b0b #e6d5ae',
        '#282116 #372d1c #443822 #f7e8c7 #d5bf91 #cbb17f #6c5734 #efcb86 #51401f #ffe4ac #302718',
        {'light':{'document-bg':'url("resources/papyrus-fibers.svg"),linear-gradient(90deg,#ba975223,transparent 5%,transparent 94%,#ba975233),var(--surface)','document-shadow':'inset 3px 0 8px #946a2722,4px 6px 12px #69512825','panel-shadow':'inset 0 1px #fff7,0 2px 3px #71551b15'},'dark':{'document-bg':'url("resources/papyrus-fibers.svg"),linear-gradient(90deg,#0002,transparent 6%,transparent 94%,#0003),var(--surface)','document-shadow':'inset 3px 0 8px #0003,4px 6px 12px #0004','panel-shadow':'inset 0 1px #a88b4c22,0 2px 3px #0003'}})
    add('jornal','Jornal','Masthead serifado, capitulares, filetes duplos e leitura editorial.',['libre-baskerville','source-serif-4'],{
        'font-heading':'"Plan Baskerville", Georgia, serif','font-reading':'"Plan Serif", Georgia, serif','hero-weight':'700','heading-weight':'700','hero-case':'uppercase','heading-case':'uppercase','hero-tracking':'-.045em','heading-tracking':'-.01em','hero-scale':'.92','radius':'0px','radius-md':'0px','radius-control':'0px','radius-sm':'0px','radius-media':'0px',
        'hero-rule':'5px double var(--text)','hero-ornament-space':'18px','panel-border-width':'1px','panel-border-color':'var(--text)','document-top-border':'5px double var(--text)','document-heading-rule':'1px solid var(--text)','document-heading-padding':'18px','small-label-font':'var(--mono)','brand-font':'"Plan Baskerville", Georgia, serif','brand-case':'uppercase','chrome-border':'3px double var(--text)',
        'dropcap-size':'3.4em','dropcap-line-height':'.85','dropcap-float':'left','dropcap-margin':'.1em .12em 0 0','dropcap-font':'"Plan Baskerville", Georgia, serif','selected-marker-opacity':'1','selected-border':'var(--text)','hover-border':'var(--text)','hover-bg':'var(--accent-soft)','duration':'0ms','scroll-behavior':'auto'},
        '#f5f3ee #fcfbf7 #e8e5de #201f1c #504e47 #5b5850 #a6a196 #38352d #e4e0d5 #141410 #e9e6df',
        '#1b1b19 #262622 #33332d #f1eee4 #c4c0b1 #b8b2a0 #686559 #e5ddc5 #403d31 #fff5d5 #22221e',
        {'light':{f'syntax-{k}':'#343128' for k in ['keyword','string','number','name']},'dark':{f'syntax-{k}':'#e5ddc5' for k in ['keyword','string','number','name']}})
    add('moderno','Moderno','Vidro fosco, luz ambiente, profundidade e hover flutuante.',['dm-sans'],{
        'font-heading':'"Plan DM", sans-serif','hero-weight':'600','heading-weight':'600','hero-tracking':'-.055em','radius':'25px','radius-md':'18px','radius-control':'14px','radius-sm':'8px','radius-media':'18px','chrome-blur':'blur(18px)',
        'page-texture':'radial-gradient(ellipse at 85% 0,color-mix(in srgb,var(--accent) 10%,transparent),transparent 52%),radial-gradient(ellipse at 8% 70%,#a778d90d,transparent 50%)','page-texture-size':'100vw 1100px','selected-border':'color-mix(in srgb,var(--accent) 60%,var(--line))','selected-shadow':'0 3px 12px color-mix(in srgb,var(--accent) 14%,transparent)','hover-transform':'translateY(-3px)','hover-shadow':'0 8px 20px color-mix(in srgb,var(--accent) 18%,transparent)','hover-bg':'var(--accent-soft)','duration':'260ms','press-transform':'translateY(1px)'},
        '#f1f6fa #fcfeff #e1ecf3 #162d3f #465e70 #52687b #c9dce9 #135478 #d9eaf4 #0a3c59 #e5eef4',
        '#0d1724 #172538 #23354b #eaf4ff #b6cbe0 #a9bdd5 #3a506b #a2d7ff #293e56 #d4edff #111d2d',
        {'light':{'panel-bg':'linear-gradient(130deg,#ffffffed,#f5faffec)','panel-shadow':'0 12px 35px #263e5f0c,inset 0 1px #ffff','chrome-bg':'#f1f6faed'},'dark':{'panel-bg':'linear-gradient(130deg,#1b2c42,#142337)','panel-shadow':'0 14px 36px #0003,inset 0 1px #b6d8ff12','chrome-bg':'#0d1724ed'}},True)
    add('minimalista','Minimalista','Sem cartões elevados ou animações; seleção por filete e contraste.',['dm-sans'],{
        'font-heading':'"Plan DM", sans-serif','hero-weight':'400','heading-weight':'400','hero-tracking':'-.045em','radius':'0px','radius-md':'0px','radius-control':'0px','radius-sm':'0px','radius-media':'0px','panel-border-width':'0px','panel-bg':'var(--bg)','selected-bg':'transparent','selected-border':'transparent','selected-marker-opacity':'1','selected-marker-width':'2px','hover-bg':'transparent','hover-border':'transparent','duration':'0ms','scroll-behavior':'auto','document-top-border':'1px solid var(--line)'},
        '#ffffff #ffffff #eeeeee #1b1b1b #555555 #626262 #dddddd #282828 #ececec #000000 #f2f2f2',
        '#111111 #111111 #252525 #eeeeee #bdbdbd #aeaeae #353535 #eeeeee #292929 #ffffff #1b1b1b')
    add('maximalista','Maximalista','Tipografia de pôster, recortes, contornos grossos e sombras deslocadas.',['bebas-neue','dm-sans'],{
        'font-heading':'"Plan Bebas", Impact, sans-serif','font':'"Plan DM", sans-serif','hero-weight':'400','heading-weight':'400','hero-case':'uppercase','heading-case':'uppercase','hero-scale':'1.3','hero-tracking':'.01em','heading-tracking':'.025em','radius':'0px','radius-md':'0px','radius-control':'0px','radius-sm':'0px','radius-media':'0px','panel-border-width':'2px','panel-border-color':'var(--text)',
        'hero-ornament':'repeating-linear-gradient(90deg,#c6437422 0 18px,transparent 18px 23px)','hero-ornament-height':'12px','hero-ornament-space':'18px','document-border':'2px solid var(--text)','document-top-border':'2px solid var(--text)','document-padding':'30px 28px','document-padding-mobile':'24px 16px','document-heading-rule':'3px solid var(--text)','document-heading-padding':'17px','selected-border':'var(--text)','selected-shadow':'4px 4px 0 var(--text)','selected-transform':'rotate(-.6deg)','selected-sheen':'repeating-linear-gradient(120deg,transparent 0 15px,#ffffff0d 15px 20px)','selected-sheen-opacity':'1','selected-animation':'reader-laser 8s linear infinite','hover-transform':'translate(-3px,-3px)','hover-shadow':'5px 5px 0 var(--text)','hover-border':'var(--text)','hover-bg':'var(--accent-soft)','press-transform':'translate(2px,2px)','duration':'160ms','page-texture':'repeating-linear-gradient(135deg,transparent 0 30px,#9b4f6e06 30px 32px)','page-texture-size':'180px 180px'},
        '#f7e9d5 #fff9ed #ecdfc8 #29232d #5b4b53 #64515a #a08383 #75335c #ead5df #52203d #efe2cf',
        '#241c2a #332638 #423148 #faebdc #d6bdaa #c9b09e #8b6c87 #f4bdca #573947 #ffe0d8 #2b2131',
        {'light':{'panel-shadow':'6px 6px 0 #302633','document-shadow':'6px 6px 0 #302633','hero-shadow':'3px 3px #dca46255'},'dark':{'panel-shadow':'6px 6px 0 #a08794','document-shadow':'6px 6px 0 #a08794','hero-shadow':'3px 3px #a3628755'}},True)
    add('art-deco','Art Déco','Molduras geométricas, dourado, títulos espaçados e seleção estática.',['cinzel','source-serif-4'],{
        'font-heading':'"Plan Cinzel", Georgia, serif','font-reading':'"Plan Serif", Georgia, serif','heading-weight':'600','hero-weight':'600','hero-case':'uppercase','hero-tracking':'.04em','heading-tracking':'.065em','hero-scale':'.92','radius':'1px','radius-md':'1px','radius-control':'0px','radius-sm':'0px','radius-media':'1px','panel-edge-mask':'url("resources/deco-frame.svg")','panel-edge-opacity':'.9','panel-border-width':'0px',
        'hero-ornament':'linear-gradient(90deg,transparent,var(--accent),transparent)','hero-ornament-height':'3px','hero-ornament-space':'18px','document-top-border':'3px double var(--accent)','document-heading-rule':'3px double var(--line)','document-heading-padding':'17px','small-label-font':'var(--mono)','selected-border':'var(--accent)','selected-shadow':'inset 3px 0 var(--accent)','hover-border':'var(--accent)','hover-bg':'var(--accent-soft)','duration':'0ms','scroll-behavior':'auto'},
        '#f2ede1 #fcf8ed #e6dfcd #29291f #5c5947 #655f4b #c2b185 #66501a #e7ddc1 #49370d #e8e1cf',
        '#101d1c #182927 #253a34 #f3ead3 #c9bf9c #bdb18e #58664a #e4ce8d #3c422c #fff0b8 #142320')
    add('terminal','Terminal','Monoespaçada, contornos precisos e seleção sólida, sem animações.',[],{
        'font':'"Plan Mono", monospace','font-heading':'"Plan Mono", monospace','font-reading':'"Plan Inter", sans-serif','hero-weight':'600','heading-weight':'600','hero-tracking':'-.045em','heading-tracking':'-.03em','hero-scale':'.87','radius':'0px','radius-md':'0px','radius-control':'0px','radius-sm':'0px','radius-media':'0px','small-label-font':'var(--mono)','hero-rule':'1px solid var(--accent)','hero-ornament-space':'16px','selected-border':'var(--accent)','selected-marker-opacity':'1','hover-bg':'var(--accent-soft)','hover-border':'var(--accent)','duration':'0ms','scroll-behavior':'auto'},
        '#f0f7ee #f9fdf6 #e0edda #1c311d #435c40 #50684b #b1c7a6 #245a2b #dcebd5 #103d15 #e5efdf',
        '#0b140e #121f15 #1c3020 #e1f4d9 #abc9a2 #9dbb92 #345638 #a5e599 #28432b #d3ffc4 #0e1a11')
    # Darken/lighten small foreground text only when the authored palette needs it.
    def contrast(a,b):
        def lum(s):
            v=[int(s[i:i+2],16)/255 for i in (1,3,5)]
            return sum(w*(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4) for w,c in zip((.2126,.7152,.0722),v))
        lo,hi=sorted((lum(a),lum(b)))
        return (hi+.05)/(lo+.05)
    for theme in profiles:
        for mode in ('light','dark'):
            colors=theme[mode]
            backgrounds=[colors[i] for i in (0,1,2,8,10)]
            for index in (3,4,5,7):
                start=colors[index]
                if min(contrast(start,b) for b in backgrounds)>=4.7:
                    continue
                rgb=[int(start[i:i+2],16) for i in (1,3,5)]
                end=0 if mode=='light' else 255
                for step in range(1,101):
                    value='#'+''.join(f'{round(c+(end-c)*step/100):02x}' for c in rgb)
                    if min(contrast(value,b) for b in backgrounds)>=4.7:
                        colors[index]=value
                        break
    existing = {t['id']: index for index,t in enumerate(catalog['themes'])}
    for theme in profiles:
        if theme['id'] in existing:
            catalog['themes'][existing[theme['id']]] = theme
        else:
            catalog['themes'].append(theme)
    catalog['preview_default'] = 'neon-laser'
    resources()
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Appended 10 expressive profiles; previous profiles retained. Total:',len(catalog['themes']))


if __name__ == '__main__':
    main()
