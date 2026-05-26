"""
BSA Aylık Post Üreticisi v5 — Magazine Style
============================================
Beyaz BG, modular layout, foto dikdörtgen bloklarda, CAPS başlık,
numara, barkod dekorasyonu, siyah logo, web URL.
Karakterler WIDE SHOT, senaryo/sinema bağlamında.
"""
import os, sys, json, io, time, re, traceback, base64
from datetime import date, timedelta
from pathlib import Path

import requests
import numpy as np
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import cairosvg

# ── Config ──
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
MAKE_WEBHOOK = os.environ["MAKE_WEBHOOK_URL"]
MONTH_LABEL = os.environ.get("MONTH_LABEL", "Bir sonraki ay")
TARGET_YEAR = int(os.environ.get("TARGET_YEAR", "2026"))
TARGET_MONTH = int(os.environ.get("TARGET_MONTH", "7"))
POST_COUNT = int(os.environ.get("POST_COUNT", "9"))

REPO_OWNER = "burakvarlik"
REPO_NAME = "bsa-social-media"
GITHUB_RAW = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/posts"

ASSETS = Path(__file__).parent.parent / "assets"
POSTS_DIR = Path(__file__).parent.parent / "posts"
POSTS_DIR.mkdir(exist_ok=True)

TR_MONTHS = {1:"oca",2:"sub",3:"mar",4:"nis",5:"may",6:"haz",7:"tem",8:"agu",9:"eyl",10:"eki",11:"kas",12:"ara"}
TR_DAYS = {0:"pzt",1:"sali",2:"car",3:"persembe",4:"cuma",5:"cumartesi",6:"pazar"}

client = OpenAI(api_key=OPENAI_KEY)


# ── Tarih hesaplama ──
def calculate_post_dates(year, month, count):
    dates, d = [], date(year, month, 1)
    while d.month == month and len(dates) < count:
        if d.weekday() in (1, 3, 5):
            dates.append(d)
        d += timedelta(days=1)
    return dates


# ── İçerik üretimi ──
BRAND_BRIEF = """BSA (Beşiktaş Senaryo Ajansı) — Türkiye'nin profesyonel senaryo ajansı.
Resmi site: www.senaryoajansi.com

ASIL MİSYON: Yapımcılar ve senaristleri buluşturan platform. "Senaryonuzu doğru yapımcıyla buluşturun."

HİZMETLER VE LİNKLERİ:
- **Senaryo Havuzu** (www.senaryoajansi.com/senaryohavuzu) — Netflix, Amazon Prime, Disney+, HBO Max, Tabii, Gain, TOD, Exxen platformlarına proje gönderimi. ANA HİZMET.
- **Senaryo Tescili** (www.senaryoajansi.com/senaryotescil) — Yasal koruma, mesleki sorumluluk sigortası
- **Senaryo Doktorluğu** (www.senaryoajansi.com/senaryoraporlama) — Profesyonel rapor, yapısal analiz
- **Film Proje Dosyası** (www.senaryoajansi.com/filmprojedosyasi) — 4 adımlı pitch deck: Özet, Karakter, Görsel, Bütçe
- **Senaryo Sipariş** (www.senaryoajansi.com/senaryotalep) — Özel sipariş
- **Atölyeler** (www.senaryoajansi.com/atolyeler) — Eğitim

İNDİRİM: BSA2026 (tüm hizmetler)
İLETİŞİM: bilgi@senaryoajansi.com · Gayrettepe, Yazarlar Sk. 14/4, İstanbul
Instagram: @besiktasenaryoajansi · LinkedIn: var

MARKA SESI:
- **Samimi** ve **içten** — "Sizi anlıyoruz" tonu. Bir partner gibi konuşur.
- Senaristin yalnızlığını, yapımcının arayışını bilir.
- Edebi ama erişilebilir. Pazarlama klişesi yok.
- Başlıklar kısa ama davetkâr. ÖRNEK: "Yalnız değilsin.", "Buluşma noktası.", "Bekleyen hikâyen var."
"""


def generate_content(count):
    group_count = max(1, count // 3)
    prompt = f"""{BRAND_BRIEF}

Tam olarak {count} adet sosyal medya postu hazırla. ZORUNLU: {count} adet.

YAPI:
- Postlar {group_count} GRUBA bölünür, her grupta 3 post aynı hizmeti farklı açıdan anlatır.
- Tercihen Senaryo Havuzu mutlaka olsun (ana hizmet).
- Her gruptaki 3 post:
  (1) sorun/dert/empati ile başlayan post
  (2) hizmetin bir yönünü tanıtan post
  (3) call-to-action / davet postu

Her postta 6 alan:

1. **baslik** — Kısa (1-3 kelime), samimi, davetkâr. Sonunda nokta veya soru işareti.
   ÖRNEK: "Yalnız değilsin.", "Buluşma noktası.", "Bekleyen hikâyen var.", "Senin sıran.", "Bir araya gelelim."
   ÇOK UZUN OLMASIN — başlık tasarımda CAPS sans-serif gösteriliyor, max 18 karakter olsun.

2. **subtitle** — Hizmet adı (CAPS gösterilir). DEĞER ÖRNEKLERİ:
   "SENARYO HAVUZU", "SENARYO TESCİLİ", "SENARYO DOKTORLUĞU", "FİLM PROJE DOSYASI", "ATÖLYELER"
   Postun ait olduğu hizmet adını bire bir yaz.

3. **aciklama** — 1-2 cümle samimi italik açıklama. "Sizi anlıyoruz" tonu. Max 80 karakter — kısa olsun, tasarımda yerleşecek.

4. **caption** — Instagram caption 80-150 kelime. İçten, satıcı değil. Mutlaka resmi linki ekle. 3-5 hashtag.

5. **platform** — "Instagram" varsayılan. LinkedIn ~%20 yapımcı odaklı içerik için.

6. **fotograf_prompt** — gpt-image-1 İngilizce prompt. ZORUNLU kurallar:
   - **WIDE SHOT** — kişiyi UZAKTAN gör. Mekan/ortam tam görünür. NOT close-up, NOT face shot, NOT portrait.
   - Kişi: tam gövde veya gövde+orta, oturan/yazan/okuyan, screenwriting/cinema bağlamı
   - Bağlam: kişi laptop'ta yazıyor, kitaplı ofiste senaryo okuyor, sinema setinde gözlem yapıyor, masada projeyi inceliyor
   - **COLOR photograph**, photorealistic, magazine editorial (Vogue/Cosmopolitan tarzı)
   - Doğal ışık, warm tones, contemporary urban (Istanbul cafe, modern apartment, screening room, sunny office)
   - Kişi tipi: Turkish, Southern European or Mediterranean appearance. Çeşitlilik: kadın/erkek, genç/orta yaş.
   - **NO close-up faces, NO portrait shots, NO eye-level head shots**
   - ÖRNEK İYİ: "Wide shot color photograph, magazine editorial style, a Turkish woman seen from across a sunlit cafe in Istanbul, sitting at a wooden table writing on her laptop, environment fully visible with bookshelves and plants, warm golden hour light, full scene composition, photorealistic, Vogue aesthetic"
   - ÖRNEK İYİ: "Wide shot of a Mediterranean man sitting at a desk in a modern producer's office, reading a script, viewed from across the room, large window with natural light, bookshelf and film posters in background, warm color palette, magazine editorial photography, photorealistic"

ÇIKTI FORMATI — GEÇERLI JSON OBJECT:
{{"posts": [
  {{"baslik": "...", "subtitle": "SENARYO HAVUZU", "aciklama": "...", "caption": "...", "platform": "Instagram", "fotograf_prompt": "..."}},
  ... ({count} adet, gruplandırılmış sırayla)
]}}
"""
    print(f">>> GPT-4 çağrılıyor (hedef {count} post, {group_count} grup × 3)...", flush=True)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Sen BSA için editorial bir içerik direktörüsün. Her zaman talep edilen tam sayıda post üretir ve geçerli JSON formatında döndürürsün."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    print(f">>> GPT-4 yanıt: {len(raw)} ch", flush=True)
    parsed = json.loads(raw)
    posts = parsed.get("posts") if isinstance(parsed, dict) else parsed
    if not isinstance(posts, list):
        raise ValueError(f"Beklenen liste değil: {type(parsed).__name__}")
    print(f">>> {len(posts)} post döndü", flush=True)
    return posts[:count]


def generate_photo(prompt, idx):
    print(f"  [gpt-image-1 {idx+1}] foto üretiliyor...", flush=True)
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1,
    )
    b64 = resp.data[0].b64_json
    img_bytes = base64.b64decode(b64)
    print(f"  [gpt-image-1 {idx+1}] tamam ({len(img_bytes)//1024} KB)", flush=True)
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


# ── V5 Magazine Template ──

def make_logo_overlay(width=180, color="black"):
    """Beyaz logodan alpha extract, istenen renkte döndür."""
    logo = Image.open(ASSETS / "BSA_Logo_beyaz_seffaf.png").convert("L")
    lw, lh = logo.size
    target_h = int(lh * width / lw)
    logo_r = logo.resize((width, target_h), Image.LANCZOS)
    arr = np.array(logo_r).astype(np.float32)
    # Daha agresif alpha — kontrast için
    alpha = np.clip((arr - 60) * 255 / (130 - 60), 0, 255).astype(np.uint8)
    rgba = np.zeros((target_h, width, 4), dtype=np.uint8)
    if color == "white":
        rgba[..., :3] = 255
    else:
        rgba[..., :3] = 0
    rgba[..., 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def prepare_photo_block(photo, w, h):
    """Fotoğrafı verilen boyutlara cover crop."""
    pw, ph = photo.size
    ratio = max(w / pw, h / ph)
    new_w, new_h = int(pw * ratio), int(ph * ratio)
    photo = photo.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return photo.crop((left, top, left + w, top + h))


def make_barcode(width=140, height=24):
    """Dekoratif barkod görseli."""
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    rng = np.random.RandomState(42)
    x = 0
    while x < width:
        bar_w = rng.choice([1, 1, 2, 2, 3])
        if rng.random() > 0.3:
            draw.rectangle([x, 0, x + bar_w, height], fill=(0, 0, 0, 255))
        x += bar_w + rng.choice([1, 1, 2])
    return img


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;")


def wrap_description(desc, max_chars=48):
    """Açıklamayı satırlara böl."""
    lines = []
    for paragraph in desc.split("\n"):
        words = paragraph.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines[:3]  # max 3 satır


def title_words_layout(title):
    """
    Başlık kelime sayısına göre satır düzeni.
    - 1 kelime → tek satır
    - 2 kelime → her biri kendi satırında
    - 3+ kelime → 1+rest veya 2+rest
    """
    words = title.upper().split()
    if len(words) == 1:
        return [words[0]]
    elif len(words) == 2:
        return [words[0], words[1]]
    else:
        # 3 kelime: 1+2
        return [words[0], " ".join(words[1:])]


def fit_title_font(lines, max_width=620, base_size=78):
    """En uzun satıra göre font size ayarla."""
    longest = max(lines, key=len)
    char_w = base_size * 0.55  # rough avg char width
    if len(longest) * char_w > max_width:
        # küçült
        new_size = int(max_width / len(longest) / 0.55)
        return max(48, min(base_size, new_size))
    return base_size


def apply_template(photo, title, subtitle, description, number, output_path, layout="A"):
    """
    Magazine style template uygula.
    layout A: foto sağda 520×680
    layout B: foto üstte 760×460
    """
    canvas = Image.new("RGB", (1080, 1080), (255, 255, 255))
    
    title_lines = title_words_layout(title.rstrip(".?!"))
    title_lines = [xml_escape(l) for l in title_lines]
    desc_lines = [xml_escape(l) for l in wrap_description(description)]
    subtitle_esc = xml_escape(subtitle.upper())
    
    if layout == "A":
        # Foto sağda
        photo_w, photo_h = 520, 700
        photo_x, photo_y = 510, 200
        prepared = prepare_photo_block(photo, photo_w, photo_h)
        canvas.paste(prepared, (photo_x, photo_y))
        
        # Title (solda)
        font_size = fit_title_font(title_lines, max_width=420, base_size=72)
        title_svg_lines = []
        y_start = 280
        for i, l in enumerate(title_lines):
            y = y_start + i * int(font_size * 1.05)
            title_svg_lines.append(
                f'<text x="70" y="{y}" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="{font_size}" fill="#000000" letter-spacing="-2">{l}</text>'
            )
        
        # Subtitle
        subtitle_y = y_start + len(title_lines) * int(font_size * 1.05) + 30
        
        # Description
        desc_y_start = 640
        desc_svg_lines = []
        for i, l in enumerate(desc_lines):
            desc_svg_lines.append(
                f'<text x="70" y="{desc_y_start + i*32}" font-family="Georgia, serif" font-style="italic" font-size="22" fill="#444444">{l}</text>'
            )
        
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">
{chr(10).join(title_svg_lines)}
<text x="70" y="{subtitle_y}" font-family="Helvetica, Arial, sans-serif" font-weight="500" font-size="22" fill="#666666" letter-spacing="4">{subtitle_esc}</text>
{chr(10).join(desc_svg_lines)}
<text x="430" y="985" text-anchor="end" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="110" fill="#000000" letter-spacing="-4">{number:02d}</text>
<line x1="70" y1="985" x2="220" y2="985" stroke="#000000" stroke-width="2"/>
</svg>'''
    
    else:  # Layout B — Foto üstte geniş
        photo_w, photo_h = 880, 480
        photo_x, photo_y = 100, 200
        prepared = prepare_photo_block(photo, photo_w, photo_h)
        canvas.paste(prepared, (photo_x, photo_y))
        
        font_size = fit_title_font(title_lines, max_width=900, base_size=78)
        title_svg_lines = []
        y_start = 760
        for i, l in enumerate(title_lines):
            y = y_start + i * int(font_size * 1.05)
            title_svg_lines.append(
                f'<text x="70" y="{y}" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="{font_size}" fill="#000000" letter-spacing="-2">{l}</text>'
            )
        
        subtitle_y = y_start + len(title_lines) * int(font_size * 1.05) + 15
        
        desc_y_start = subtitle_y + 60
        desc_svg_lines = []
        for i, l in enumerate(desc_lines[:2]):  # max 2 line in B
            desc_svg_lines.append(
                f'<text x="70" y="{desc_y_start + i*30}" font-family="Georgia, serif" font-style="italic" font-size="20" fill="#444444">{l}</text>'
            )
        
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">
{chr(10).join(title_svg_lines)}
<text x="70" y="{subtitle_y}" font-family="Helvetica, Arial, sans-serif" font-weight="500" font-size="20" fill="#666666" letter-spacing="4">{subtitle_esc}</text>
{chr(10).join(desc_svg_lines)}
<text x="1010" y="1000" text-anchor="end" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="110" fill="#000000" letter-spacing="-4">{number:02d}</text>
</svg>'''
    
    # SVG → overlay
    buf = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=buf, output_width=1080, output_height=1080)
    buf.seek(0)
    overlay = Image.open(buf).convert("RGBA")
    canvas_rgba = canvas.convert("RGBA")
    result = Image.alpha_composite(canvas_rgba, overlay)
    
    # Logo sol üst (siyah, 180px)
    logo = make_logo_overlay(180, "black")
    result.paste(logo, (70, 70), logo)
    
    # Web URL sağ üst — PIL ile çiz (siyah, küçük caps)
    draw = ImageDraw.Draw(result)
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 18)
        draw.text((1010, 100), "WWW.SENARYOAJANSI.COM", fill=(0, 0, 0, 255), font=font, anchor="rm")
    except Exception:
        pass
    
    # Barkod sol alt
    barcode = make_barcode(140, 24)
    result.paste(barcode, (70, 990), barcode)
    
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
    print(f"BSA AYLIK POST ÜRETİMİ v5 — {MONTH_LABEL}", flush=True)
    print(f"Hedef: {POST_COUNT} post, {TR_MONTHS[TARGET_MONTH]} {TARGET_YEAR}", flush=True)
    print("=" * 60, flush=True)
    
    dates = calculate_post_dates(TARGET_YEAR, TARGET_MONTH, POST_COUNT)
    print(f"Tarihler: {[d.strftime('%d.%m') for d in dates]}", flush=True)
    
    posts = generate_content(POST_COUNT)
    
    print(f"\n>>> {len(posts)} post ile {len(dates)} tarih için döngü\n", flush=True)
    
    success = 0
    for i, (post_date, post_data) in enumerate(zip(dates, posts)):
        try:
            baslik = post_data["baslik"]
            subtitle = post_data.get("subtitle", "")
            aciklama = post_data["aciklama"]
            caption = post_data["caption"]
            platform = post_data.get("platform", "Instagram")
            photo_prompt = post_data.get("fotograf_prompt") or post_data.get("fotoğraf_prompt", "Wide shot color photograph of a screenwriter at desk")
            
            fname = f"{post_date.strftime('%d')}-{TR_MONTHS[TARGET_MONTH]}-{TR_DAYS[post_date.weekday()]}-{slugify(baslik)}.png"
            out_path = POSTS_DIR / fname
            
            print(f"─── Post {i+1}/{len(posts)} — {post_date.strftime('%d %b')} ─── {baslik} [{subtitle}]", flush=True)
            
            photo = generate_photo(photo_prompt, i)
            
            # Layout rotation: A, B alternate
            layout = "A" if i % 2 == 0 else "B"
            print(f"  [Template] layout={layout}, numara={i+1}", flush=True)
            apply_template(photo, baslik, subtitle, aciklama, i + 1, out_path, layout=layout)
            
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
    
    print(f"\n{'='*60}\n✓ TAMAMLANDI — {success}/{len(dates)} post\n{'='*60}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
