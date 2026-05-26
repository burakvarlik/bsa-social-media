"""
BSA Aylık Post Üreticisi
========================
1. OpenAI GPT-4 → 8 post için editorial başlık + açıklama + caption üretir
2. DALL-E 3 → her post için sinematik siyah-beyaz foto üretir
3. BSA master template uygulanır (Georgia italic, kırmızı nokta, logo)
4. PNG dosyaları posts/ klasörüne yazılır
5. Make webhook'a POST → data store'a kayıt eklenir
"""

import os
import sys
import json
import io
import time
import base64
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import requests
import numpy as np
from openai import OpenAI
from PIL import Image
import cairosvg


# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
MAKE_WEBHOOK = os.environ["MAKE_WEBHOOK_URL"]
MONTH_LABEL = os.environ.get("MONTH_LABEL", "Bir sonraki ay")
TARGET_YEAR = int(os.environ.get("TARGET_YEAR", "2026"))
TARGET_MONTH = int(os.environ.get("TARGET_MONTH", "7"))
POST_COUNT = int(os.environ.get("POST_COUNT", "8"))

REPO_OWNER = "burakvarlik"
REPO_NAME = "bsa-social-media"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/posts"

ASSETS = Path(__file__).parent.parent / "assets"
POSTS_DIR = Path(__file__).parent.parent / "posts"
POSTS_DIR.mkdir(exist_ok=True)

client = OpenAI(api_key=OPENAI_KEY)


# ──────────────────────────────────────────────────────────────
# 1. POST TARİHLERİNİ HESAPLA
# Sal/Per/Cmt günlerini bul, POST_COUNT kadar al
# ──────────────────────────────────────────────────────────────
def calculate_post_dates(year, month, count):
    """Verilen ay için Sal(1)/Per(3)/Cmt(5) günlerinden ilk `count` adet."""
    dates = []
    d = date(year, month, 1)
    while d.month == month and len(dates) < count:
        if d.weekday() in (1, 3, 5):  # Tue, Thu, Sat
            dates.append(d)
        d += timedelta(days=1)
    return dates


# ──────────────────────────────────────────────────────────────
# 2. GPT-4: İÇERİK ÜRETİMİ
# Marka sesini koruyan editorial başlık + açıklama + caption
# ──────────────────────────────────────────────────────────────
BRAND_BRIEF = """
Sen BSA (Beşiktaş Senaryo Ajansı) için sosyal medya editörüsün. 
Marka kimliği: bir reklam ajansı değil, bir edebiyat dergisi. 
Tonu: A24, Criterion Collection, The Gentlewoman dergisi, Notos dergisi seviyesinde. 
Mesafeli, evocative, edebi. Asla pazarlama klişesi kullanma.

BSA'nın hizmetleri:
- Senaryo Tescili (mesleki sorumluluk sigortasıyla)
- Senaryo Doktorluğu (profesyonel rapor)
- Senaryo Havuzu (8 platform: Netflix, Amazon, Disney+, HBO Max, Tabii, Gain, TOD, Exxen)
- Film Proje Dosyası (pitch deck)
- Atölyeler (Temel Senaryo, Karakter Geliştirme, Dizi Anlatımı)
- BSA2026 indirim kodu (Haziran'a özel, tüm hizmetlerde)
- Yıllık BSA Senaryo Yarışması

URL: www.senaryoajansi.com
Instagram handle: @besiktasenaryoajansi
"""

CONTENT_PROMPT = """
{brand}

GÖREV: {month_label} için {count} adet sosyal medya postu hazırla.

Her post için 5 alan ÜRET:

1. **baslik** — Başlık. Bir film ismi gibi olmalı. Çok kısa (1-3 kelime), evocative, mesafeli.
   ÖRNEK: "Tescil.", "Sekiz kapı.", "Şimdi ne?", "Atölye.", "Sıradaki sahne."
   YANLIŞ: "Senaryomu nasıl korurum?", "5 ipucu", "Yapımcılar için en iyi platformlar"

2. **aciklama** — 1-2 cümle italic açıklama. Başlığı tamamlar. Liste değil, italic edebi cümle.
   ÖRNEK: "Bir senaryonun ilk koruması, son sığınağı. Bir milyon liralık mesleki sorumlulukla."
   YANLIŞ: "Senaryonuzu koruyun! Hızlı süreç, ucuz fiyat, harika!"

3. **caption** — Instagram caption. 80-150 kelime. Bir editör gibi yaz, satıcı gibi değil.
   Hashtag (3-5 tane), CTA (sade — link + kod), bullet yok satışsız.

4. **platform** — "Instagram" veya "LinkedIn" (LinkedIn yapımcı odaklı içerik için)

5. **fotoğraf_prompt** — DALL-E 3 için İngilizce sahne tarifi. 
   Tüm postlar SİYAH BEYAZ + SİNEMATİK olmalı (Roger Deakins, 35mm grain).
   Bağlamla uyumlu nesne/sahne seç:
     - Tescil → typed screenplay page, vintage paper
     - Havuz/yapımcı → screening room interior, projector booth
     - Doktorluk → handwritten notes, fountain pen, manuscript editing
     - Proje Dosyası → opened pitch document, design boards
     - Atölye → film camera (ARRI), behind-the-scenes silhouettes
     - Genel → vintage typewriter, ink, theater seats, film reels
   Format: "Black and white cinematic close-up of [object/scene], [lighting detail], 35mm grain, Roger Deakins style, professional film still, dramatic shadows, 1:1 aspect ratio"

İÇERİK DAĞILIMI ({count} post için dengeli ol):
- 4-5 hizmet odaklı (Tescil, Doktorluk, Havuz, Proje Dosyası)
- 1-2 yapımcı/sektör (LinkedIn'e uygun)
- 1 atölye veya yarışma
- 1 ay sonu / dönem analizi

ÇIKTI: JSON array, başka hiçbir şey yok. Markdown code fence kullanma.
[{{"baslik": "...", "aciklama": "...", "caption": "...", "platform": "Instagram", "fotoğraf_prompt": "..."}}, ...]
"""

def generate_content():
    prompt = CONTENT_PROMPT.format(
        brand=BRAND_BRIEF.strip(),
        month_label=MONTH_LABEL,
        count=POST_COUNT,
    )
    print(f"[1/4] GPT-4 ile {POST_COUNT} post içeriği üretiliyor...")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    print(f"    GPT-4 yanıt: {raw[:200]}...", flush=True)
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                parsed = v
                break
        else:
            # Tek post objesi gelmişse listeye sar
            if "baslik" in parsed:
                parsed = [parsed]
    print(f"    ✓ {len(parsed)} post üretildi", flush=True)
    return parsed


# ──────────────────────────────────────────────────────────────
# 3. DALL-E 3: FOTO ÜRETİMİ
# ──────────────────────────────────────────────────────────────
def generate_photo(prompt, idx):
    print(f"[2/4] DALL-E 3: foto {idx+1}/{POST_COUNT} üretiliyor...")
    resp = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        style="natural",
        n=1,
    )
    url = resp.data[0].url
    img_bytes = requests.get(url, timeout=60).content
    print(f"    ✓ foto indirildi ({len(img_bytes) // 1024} KB)")
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


# ──────────────────────────────────────────────────────────────
# 4. BSA MASTER TEMPLATE
# ──────────────────────────────────────────────────────────────
def make_logo_overlay(width=140):
    """BSA logosu alpha kanalıyla render edilir."""
    logo_path = ASSETS / "BSA_Logo_beyaz_seffaf.png"
    logo = Image.open(logo_path).convert("L")
    lw, lh = logo.size
    target_h = int(lh * width / lw)
    logo_r = logo.resize((width, target_h), Image.LANCZOS)
    arr = np.array(logo_r).astype(np.float32)
    alpha = np.clip((arr - 80) * 255 / (130 - 80), 0, 255).astype(np.uint8)
    rgba = np.zeros((target_h, width, 4), dtype=np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def prepare_photo(photo):
    """Merkez kare crop + film grain."""
    w, h = photo.size
    short = min(w, h)
    left = (w - short) // 2
    top = (h - short) // 2
    sq = photo.crop((left, top, left + short, top + short))
    if sq.size != (1080, 1080):
        sq = sq.resize((1080, 1080), Image.LANCZOS)
    sq = sq.convert("RGBA")
    arr = np.array(sq).astype(np.int16)
    noise = np.random.randint(-7, 7, (1080, 1080, 1)).repeat(3, axis=2)
    arr[..., :3] = np.clip(arr[..., :3] + noise, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def choose_title_layout(title):
    """Başlık uzunluğuna göre layout & font size."""
    n = len(title)
    if n <= 9:        # "Tescil.", "Atölye."
        return "single", 200
    elif n <= 12:     # "BSA2026.", "Şimdi ne?"
        return "single", 165
    elif n <= 14:     # "Sekiz kapı.", "Üç avantaj."
        return "single", 140
    elif n <= 18:     # "Senaryo Doktorluğu."
        return "two_line", 118
    else:
        return "two_line", 100


def title_svg(title, mode, fs):
    main, last = title[:-1], title[-1]
    if mode == "single":
        return f'<text x="60" y="920" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{main}<tspan fill="#8B1A1A">{last}</tspan></text>'
    parts = title.rsplit(" ", 1)
    line1, line2 = parts[0], parts[1]
    return f'''<text x="60" y="830" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{line1}</text>
<text x="60" y="945" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{line2[:-1]}<tspan fill="#8B1A1A">{line2[-1]}</tspan></text>'''


def description_svg(description):
    """Açıklamayı 1 veya 2 satıra otomatik böl."""
    if "\n" in description:
        lines = description.split("\n")[:2]
    else:
        # ~52 karakterde kır
        words = description.split()
        line1, line2 = "", ""
        for w in words:
            if len(line1) + len(w) + 1 <= 52:
                line1 = (line1 + " " + w).strip()
            else:
                line2 = (line2 + " " + w).strip()
        lines = [line1, line2] if line2 else [line1]
    out = []
    for i, l in enumerate(lines):
        # Escape XML
        l = l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        out.append(f'<text x="60" y="{1000 + i * 28}" font-family="Georgia, serif" font-style="italic" font-size="22" fill="#ffffff" opacity="0.72">{l}</text>')
    return "\n".join(out)


def build_overlay_svg(title, description):
    mode, fs = choose_title_layout(title)
    title_escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">
<defs>
<linearGradient id="tf" x1="0%" y1="0%" x2="0%" y2="100%">
<stop offset="0%" stop-color="#0a0908" stop-opacity="0.55"/>
<stop offset="100%" stop-color="#0a0908" stop-opacity="0"/>
</linearGradient>
<linearGradient id="bf" x1="0%" y1="0%" x2="0%" y2="100%">
<stop offset="0%" stop-color="#0a0908" stop-opacity="0"/>
<stop offset="38%" stop-color="#0a0908" stop-opacity="0.78"/>
<stop offset="100%" stop-color="#0a0908" stop-opacity="0.98"/>
</linearGradient>
</defs>
<rect x="0" y="0" width="1080" height="220" fill="url(#tf)"/>
<rect x="0" y="600" width="1080" height="480" fill="url(#bf)"/>
{title_svg(title_escaped, mode, fs)}
{description_svg(description)}
<line x1="60" y1="1055" x2="1020" y2="1055" stroke="#ffffff" stroke-width="0.5" opacity="0.3"/>
<text x="60" y="1078" font-family="Helvetica, sans-serif" font-weight="500" font-size="11" letter-spacing="2.5" fill="#ffffff" opacity="0.65">SENARYOAJANSI.COM</text>
<text x="1020" y="1078" text-anchor="end" font-family="Georgia, serif" font-style="italic" font-size="12" fill="#ffffff" opacity="0.5">@besiktasenaryoajansi</text>
</svg>'''


def apply_template(photo, title, description, output_path):
    """BSA master template'i fotoya uygula."""
    photo_grain = prepare_photo(photo)
    svg = build_overlay_svg(title, description)
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=buf, output_width=1080, output_height=1080)
    buf.seek(0)
    overlay = Image.open(buf).convert("RGBA")
    result = Image.alpha_composite(photo_grain, overlay)
    logo = make_logo_overlay(140)
    result.paste(logo, (60, 55), logo)
    result.convert("RGB").save(output_path, quality=95)


# ──────────────────────────────────────────────────────────────
# 5. MAKE WEBHOOK'A POST
# ──────────────────────────────────────────────────────────────
def push_to_make(record):
    print(f"[4/4] Make webhook'a gönderiliyor: {record['tarih']}")
    resp = requests.post(MAKE_WEBHOOK, json=record, timeout=30)
    if resp.status_code == 200:
        print(f"    ✓ data store'a eklendi")
    else:
        print(f"    ✗ webhook hatası: {resp.status_code} {resp.text[:200]}")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
TR_MONTHS = {1:"oca",2:"sub",3:"mar",4:"nis",5:"may",6:"haz",7:"tem",8:"agu",9:"eyl",10:"eki",11:"kas",12:"ara"}
TR_DAYS = {0:"pzt",1:"sali",2:"car",3:"persembe",4:"cuma",5:"cumartesi",6:"pazar"}

DEBUG_LOG = []

def dlog(msg):
    """Hem print et hem debug.txt için sakla."""
    print(msg, flush=True)
    DEBUG_LOG.append(msg)
    # Her log satırında debug.txt'i güncelle (her ihtimale karşı)
    with open("debug.txt", "w") as f:
        f.write("\n".join(DEBUG_LOG))

def main():
    dlog("=" * 60)
    dlog(f"BSA AYLIK POST ÜRETİMİ — {MONTH_LABEL}")
    dlog(f"Hedef: {POST_COUNT} post, {TR_MONTHS[TARGET_MONTH]} {TARGET_YEAR}")
    dlog("=" * 60)
    
    dates = calculate_post_dates(TARGET_YEAR, TARGET_MONTH, POST_COUNT)
    dlog(f"Tarihler: {[d.strftime('%d.%m') for d in dates]}")
    
    dlog(f"OPENAI_API_KEY var mı: {bool(os.environ.get('OPENAI_API_KEY'))}")
    dlog(f"OPENAI_API_KEY uzunluk: {len(os.environ.get('OPENAI_API_KEY', ''))}")
    dlog(f"MAKE_WEBHOOK: {os.environ.get('MAKE_WEBHOOK_URL', '')[:50]}...")
    dlog("\n>>> generate_content() çağrılıyor...")
    posts = generate_content()
    dlog(f"<<< generate_content() döndü: type={type(posts).__name__}, içerik (ilk 500ch): {str(posts)[:500]}")
    if len(posts) < len(dates):
        print(f"UYARI: GPT-4 sadece {len(posts)} post üretti, {len(dates)} tarih var.")
    
    dlog(f"\n>>> Döngüye giriliyor: {len(dates)} tarih, {len(posts) if hasattr(posts, '__len__') else '?'} post")
    for i, (post_date, post_data) in enumerate(zip(dates, posts)):
        baslik = post_data["baslik"]
        aciklama = post_data["aciklama"]
        caption = post_data["caption"]
        platform = post_data.get("platform", "Instagram")
        photo_prompt = post_data.get("fotoğraf_prompt") or post_data.get("fotograf_prompt", "Black and white cinematic still")
        
        # Dosya adı
        slug = baslik.lower().replace(".", "").replace("?", "").replace(" ", "-").replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")[:30]
        fname = f"{post_date.strftime('%d')}-{TR_MONTHS[TARGET_MONTH]}-{TR_DAYS[post_date.weekday()]}-{slug}.png"
        out_path = POSTS_DIR / fname
        
        print(f"\n─── Post {i+1}/{len(posts)} — {post_date.strftime('%d %b')} ─── {baslik}")
        
        try:
            photo = generate_photo(photo_prompt, i)
            print(f"[3/4] Template uygulanıyor...")
            apply_template(photo, baslik, aciklama, out_path)
            print(f"    ✓ {fname}")
            
            image_url = f"{GITHUB_RAW_BASE}/{fname}"
            record = {
                "tarih": post_date.strftime("%Y-%m-%d"),
                "platform": platform,
                "baslik": baslik,
                "aciklama": aciklama,
                "caption": caption,
                "image_url": image_url,
                "dosya": fname,
            }
            push_to_make(record)
            time.sleep(1)
            
        except Exception as e:
            print(f"    ✗ HATA: {e}")
            continue
    
    print("\n" + "=" * 60)
    print(f"✓ TAMAMLANDI — {MONTH_LABEL}")
    dlog("=" * 60)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        print("=" * 60, flush=True)
        print(f"FATAL ERROR: {type(e).__name__}: {e}", flush=True)
        print("=" * 60, flush=True)
        traceback.print_exc()
        # debug.txt'i her durumda yaz
        with open("debug.txt", "w") as f:
            f.write(f"FATAL: {type(e).__name__}: {e}\n\n")
            f.write(traceback.format_exc())
        sys.exit(1)
