# BSA Sosyal Medya — Tam Otomasyon

Beşiktaş Senaryo Ajansı'nın Instagram & LinkedIn hesapları için aylık post üretim sistemi.

## Akış

```
GitHub Action (her ay 25'inde tetiklenir)
  → OpenAI GPT-4 başlık + açıklama + caption üretir
  → DALL-E 3 sinematik foto üretir
  → BSA master template uygulanır
  → posts/ klasörüne commit edilir
  → Make webhook'una POST → data store'a kayıt eklenir

Her Sal/Per/Cmt 18:00:
  → Make Senaryo A → Telegram'a önizleme
  → "onayla" → Make Senaryo B → Instagram'a yayın
```

## Manuel Tetikleme

GitHub → Actions → "Aylık BSA Postlarını Üret" → "Run workflow"
Ay etiketini ve hedef ay/yılı gir.

## Klasörler

- `.github/workflows/` — Otomasyon
- `scripts/` — Python üretici
- `assets/` — Logo, font, vs.
- `posts/` — Üretilmiş görseller (otomatik commit edilir)

## Marka Sesi

Bir reklam ajansı değil, bir edebiyat dergisi.
A24 · Criterion Collection · The Gentlewoman · Notos.

