"""
BSA Aylık Post Üreticisi v2
============================
Her ay 8 yeni post üretir: GPT-4 (içerik) + DALL-E 3 (foto) + BSA template + GitHub + Make webhook
"""
import os, sys, json, io, time, re, traceback
from datetime import date, timedelta
from pathlib import Path

import requests
import numpy as np
from openai import OpenAI
from PIL import Image
import cairosvg

# ── Config ──
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
MAKE_WEBHOOK = os.environ["MAKE_WEBHOOK_URL"]
MONTH_LABEL = os.environ.get("MONTH_LABEL", "Bir sonraki ay")
TARGET_YEAR = int(os.environ.get("TARGET_YEAR", "2026"))
TARGET_MONTH = int(os.environ.get("TARGET_MONTH", "7"))
POST_COUNT = int(os.environ.get("POST_COUNT", "8"))

REPO_OWNER = "burakvarlik"
REPO_NAME = "bsa-social-media"
GITHUB_RAW = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/posts"

ASSETS = Path(__file__).parent.parent / "assets"
POSTS_DIR = Path(__file__).parent.parent / "posts"
POSTS_DIR.mkdir(exist_ok=True)

TR_MONTHS = {1:"oca",2:"sub",3:"mar",4:"nis",5:"may",6:"haz",7:"tem",8:"agu",9:"eyl",10:"eki",11:"kas",12:"ara"}
TR_DAYS = {0:"pzt",1:"sali",2:"car",3:"persembe",4:"cuma",5:"cumartesi",6:"pazar"}

client = OpenAI(api_key=OPENAI_KEY)

# ── Yardımcılar ──

def calculate_post_dates(year, month, count):
    """Verilen ay için Sal/Per/Cmt günleri."""
    dates, d = [], date(year, month, 1)
    while d.month == month and len(dates) < count:
        if d.weekday() in (1, 3, 5):
            dates.append(d)
        d += timedelta(days=1)
    return dates


BRAND_BRIEF = """BSA (Beşiktaş Senaryo Ajansı) — Türkiye'nin önde gelen senaryo ajansı.
Marka tonu: A24, Criterion, The Gentlewoman, Notos dergi seviyesi. Edebi, mesafeli, evocative.
Asla pazarlama klişesi yok. Başlıklar bir film ismi gibi: kısa, edebi.

Hizmetler: Senaryo Tescili, Senaryo Doktorluğu, Senaryo Havuzu (8 platform: Netflix, Amazon, Disney+, HBO Max, Tabii, Gain, TOD, Exxen), Film Proje Dosyası, Atölyeler.
İndirim kodu: BSA2026 (Haziran'da tüm hizmetlere). URL: www.senaryoajansi.com. Instagram: @besiktasenaryoajansi"""


def generate_content(count):
    """N adet post üret. Her zaman tam N adet array döndürür."""
    prompt = f"""{BRAND_BRIEF}

Tam olarak {count} adet sosyal medya postu hazırla. ZORUNLU: {count} adet, ne eksik ne fazla.

Her postta 5 alan olmalı:
1. baslik — Bir film ismi gibi, 1-3 kelime, sonunda nokta veya soru işareti. ÖRNEK: "Tescil.", "Sekiz kapı.", "Şimdi ne?", "Sıradaki sahne.", "Yarı yıl."
2. aciklama — 1-2 italik cümle, başlığı tamamlar. Liste değil, edebi.
3. caption — Instagram caption (80-150 kelime). Sade, edebi, satıcı değil. 3-5 hashtag.
4. platform — "Instagram" veya "LinkedIn" (LinkedIn'i yapımcı içerikleri için kullan, ~%30)
5. fotograf_prompt — DALL-E 3 İngilizce prompt. SİYAH BEYAZ + SİNEMATİK + 35mm grain. Konuyla uyumlu nesne seç (typewriter, screenplay, projector, theater seats, film camera, fountain pen, manuscript).

İçerik dağılımı:
- ~50% hizmet tanıtımı (Tescil, Doktorluk, Havuz, Proje Dosyası — değişerek)
- ~25% sektör/yapımcı (LinkedIn için)
- ~15% atölye/yarışma
- ~10% genel marka (ay başı/sonu, kültür)

ÇIKTI FORMATI — GEÇERLI JSON OBJECT:
{{"posts": [...]}}

Yani DIŞ KATMAN obje, içinde "posts" anahtarı, değer olarak {count} elemanlı array.
ÖRNEK:
{{"posts": [
  {{"baslik": "Tescil.", "aciklama": "...", "caption": "...", "platform": "Instagram", "fotograf_prompt": "Black and white cinematic..."}},
  ...
]}}
"""
    print(f">>> GPT-4 çağrılıyor (hedef {count} post)...", flush=True)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Sen BSA için editorial bir içerik direktörüsün. Her zaman talep edilen tam sayıda post üretirsin ve geçerli JSON formatında döndürürsün."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    print(f">>> GPT-4 yanıt uzunluğu: {len(raw)} ch", flush=True)
    
    parsed = json.loads(raw)
    
    # Standart wrapper: {"posts": [...]}
    posts = parsed.get("posts") if isinstance(parsed, dict) else parsed
    if not isinstance(posts, list):
        # Backup: dict'in herhangi bir array değeri
        for v in (parsed.values() if isinstance(parsed, dict) else []):
            if isinstance(v, list) and v:
                posts = v
                break
    
    if not isinstance(posts, list):
        raise ValueError(f"Beklenen liste değil, geldi: {type(parsed).__name__} — {str(parsed)[:300]}")
    
    print(f">>> {len(posts)} post döndü", flush=True)
    if len(posts) < count:
        print(f"!!! UYARI: {count} istendi, {len(posts)} geldi", flush=True)
    
    return posts[:count]


def generate_photo(prompt, idx):
    import base64
    print(f"  [gpt-image-1 {idx+1}] foto üretiliyor...", flush=True)
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1,
    )
    # gpt-image-1 b64_json döndürür
    b64 = resp.data[0].b64_json
    img_bytes = base64.b64decode(b64)
    print(f"  [gpt-image-1 {idx+1}] tamam ({len(img_bytes)//1024} KB)", flush=True)
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


# ── BSA Template (önceki kod birebir) ──

def make_logo_overlay(width=140):
    logo = Image.open(ASSETS / "BSA_Logo_beyaz_seffaf.png").convert("L")
    lw, lh = logo.size
    target_h = int(lh * width / lw)
    logo_r = logo.resize((width, target_h), Image.LANCZOS)
    arr = np.array(logo_r).astype(np.float32)
    alpha = np.clip((arr - 80) * 255 / (130 - 80), 0, 255).astype(np.uint8)
    rgba = np.zeros((target_h, width, 4), dtype=np.uint8)
    rgba[..., :3] = 255; rgba[..., 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def prepare_photo(photo):
    w, h = photo.size
    short = min(w, h)
    left, top = (w - short)//2, (h - short)//2
    sq = photo.crop((left, top, left + short, top + short))
    if sq.size != (1080, 1080):
        sq = sq.resize((1080, 1080), Image.LANCZOS)
    sq = sq.convert("RGBA")
    arr = np.array(sq).astype(np.int16)
    noise = np.random.randint(-7, 7, (1080, 1080, 1)).repeat(3, axis=2)
    arr[..., :3] = np.clip(arr[..., :3] + noise, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def choose_layout(title):
    n = len(title)
    if n <= 9:   return "single", 200
    if n <= 12:  return "single", 165
    if n <= 14:  return "single", 140
    if n <= 18:  return "two_line", 118
    return "two_line", 100


def xml_escape(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("'","&apos;")


def title_svg(title, mode, fs):
    title = xml_escape(title)
    main, last = title[:-1], title[-1]
    if mode == "single":
        return f'<text x="60" y="920" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{main}<tspan fill="#8B1A1A">{last}</tspan></text>'
    parts = title.rsplit(" ", 1)
    line1, line2 = parts[0], parts[1]
    return f'<text x="60" y="830" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{line1}</text>\n<text x="60" y="945" font-family="Georgia, serif" font-style="italic" font-size="{fs}" fill="#ffffff" letter-spacing="-3">{line2[:-1]}<tspan fill="#8B1A1A">{line2[-1]}</tspan></text>'


def description_svg(desc):
    if "\n" in desc:
        lines = desc.split("\n")[:2]
    else:
        words = desc.split()
        line1, line2 = "", ""
        for w in words:
            if len(line1) + len(w) + 1 <= 52:
                line1 = (line1 + " " + w).strip()
            else:
                line2 = (line2 + " " + w).strip()
        lines = [line1, line2] if line2 else [line1]
    out = []
    for i, l in enumerate(lines):
        out.append(f'<text x="60" y="{1000+i*28}" font-family="Georgia, serif" font-style="italic" font-size="22" fill="#ffffff" opacity="0.72">{xml_escape(l)}</text>')
    return "\n".join(out)


def build_overlay(title, desc):
    mode, fs = choose_layout(title)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">
<defs>
<linearGradient id="tf" x1="0%" y1="0%" x2="0%" y2="100%">
<stop offset="0%" stop-color="#0a0908" stop-opacity="0.55"/><stop offset="100%" stop-color="#0a0908" stop-opacity="0"/>
</linearGradient>
<linearGradient id="bf" x1="0%" y1="0%" x2="0%" y2="100%">
<stop offset="0%" stop-color="#0a0908" stop-opacity="0"/><stop offset="38%" stop-color="#0a0908" stop-opacity="0.78"/><stop offset="100%" stop-color="#0a0908" stop-opacity="0.98"/>
</linearGradient>
</defs>
<rect x="0" y="0" width="1080" height="220" fill="url(#tf)"/>
<rect x="0" y="600" width="1080" height="480" fill="url(#bf)"/>
{title_svg(title, mode, fs)}
{description_svg(desc)}
<line x1="60" y1="1055" x2="1020" y2="1055" stroke="#ffffff" stroke-width="0.5" opacity="0.3"/>
<text x="60" y="1078" font-family="Helvetica, sans-serif" font-weight="500" font-size="11" letter-spacing="2.5" fill="#ffffff" opacity="0.65">SENARYOAJANSI.COM</text>
<text x="1020" y="1078" text-anchor="end" font-family="Georgia, serif" font-style="italic" font-size="12" fill="#ffffff" opacity="0.5">@besiktasenaryoajansi</text>
</svg>'''


def apply_template(photo, title, desc, output_path):
    photo_grain = prepare_photo(photo)
    svg = build_overlay(title, desc)
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=buf, output_width=1080, output_height=1080)
    buf.seek(0)
    overlay = Image.open(buf).convert("RGBA")
    result = Image.alpha_composite(photo_grain, overlay)
    logo = make_logo_overlay(140)
    result.paste(logo, (60, 55), logo)
    result.convert("RGB").save(output_path, quality=95)


def slugify(s):
    s = s.lower().replace("ı","i").replace("ş","s").replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:30]


def push_to_make(record):
    print(f"  [Make] webhook'a gönderiliyor: {record['tarih']}", flush=True)
    r = requests.post(MAKE_WEBHOOK, json=record, timeout=30)
    print(f"  [Make] yanıt: {r.status_code} {r.text[:100]}", flush=True)


# ── Main ──

def main():
    print("=" * 60, flush=True)
    print(f"BSA AYLIK POST ÜRETİMİ — {MONTH_LABEL}", flush=True)
    print(f"Hedef: {POST_COUNT} post, {TR_MONTHS[TARGET_MONTH]} {TARGET_YEAR}", flush=True)
    print(f"OPENAI_API_KEY: {'var' if OPENAI_KEY else 'YOK'} ({len(OPENAI_KEY)} ch)", flush=True)
    print(f"MAKE_WEBHOOK: {MAKE_WEBHOOK[:60]}", flush=True)
    print("=" * 60, flush=True)
    
    dates = calculate_post_dates(TARGET_YEAR, TARGET_MONTH, POST_COUNT)
    print(f"Tarihler: {[d.strftime('%d.%m') for d in dates]}", flush=True)
    
    posts = generate_content(POST_COUNT)
    
    if not posts:
        print("HATA: GPT-4'ten hiç post gelmedi", flush=True)
        sys.exit(1)
    
    print(f"\n>>> {len(posts)} post ile {len(dates)} tarih için döngü başlıyor\n", flush=True)
    
    success = 0
    for i, (post_date, post_data) in enumerate(zip(dates, posts)):
        try:
            baslik = post_data["baslik"]
            aciklama = post_data["aciklama"]
            caption = post_data["caption"]
            platform = post_data.get("platform", "Instagram")
            photo_prompt = post_data.get("fotograf_prompt") or post_data.get("fotoğraf_prompt", "Black and white cinematic still life")
            
            fname = f"{post_date.strftime('%d')}-{TR_MONTHS[TARGET_MONTH]}-{TR_DAYS[post_date.weekday()]}-{slugify(baslik)}.png"
            out_path = POSTS_DIR / fname
            
            print(f"─── Post {i+1}/{len(posts)} — {post_date.strftime('%d %b')} ─── {baslik}", flush=True)
            
            photo = generate_photo(photo_prompt, i)
            print(f"  [Template] uygulanıyor...", flush=True)
            apply_template(photo, baslik, aciklama, out_path)
            print(f"  [Template] kaydedildi: {fname}", flush=True)
            
            push_to_make({
                "tarih": post_date.strftime("%Y-%m-%d"),
                "platform": platform,
                "baslik": baslik,
                "aciklama": aciklama,
                "caption": caption,
                "image_url": f"{GITHUB_RAW}/{fname}",
                "dosya": fname,
            })
            success += 1
            time.sleep(1)
        except Exception as e:
            print(f"  ✗ HATA: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}", flush=True)
    print(f"✓ TAMAMLANDI — {success}/{len(dates)} post üretildi", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
