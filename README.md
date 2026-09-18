# Weekly Podcast Bot

خودکارسازی پادکست هفتگی **کوهنامه** — انتخاب پربازدیدترین مطالب از کانال‌های تلگرامی کوهنوردی و تبدیل به فایل صوتی تک‌گوینده.

## نحوه کار

```
هر هفته (یکشنبه ۸ صبح تهران)
    │
    ├─ ۱. Telethon → ۷ روز اخبار از ۷۱ کانال + تعداد بازدید
    ├─ ۲. فیلتر + انتخاب ۲ پست پربازدید هر کانال
    ├─ ۳. Gemini Flash → سناریو بدنه پادکست (فقط خبرها، بدون مقدمه/جمعبندی)
    ├─ ۴. Gemini Live TTS (صدای فرشید/Charon) → تولید ۳ بخش صوتی جداگانه:
    │       • متن آغاز  → صدا + موسیقی اینترو
    │       • بدنه اصلی  → فقط صدا
    │       • متن پایان  → صدا + موسیقی آوترو
    ├─ ۵. ترکیب: آغاز + موزیک اول + بدنه + خداحافظی + موزیک دوم
    ├─ ۶. ffmpeg → MP3 (۶۴kbps، حجم مناسب)
    ├─ ۷. Bot API → ارسال به گروه تلگرام
    └─ ۸. حذف فایل‌های موقت
```

## ساختار پادکست (نسخه ۱.۰.۰)

```
[متن آغازِ TTS] → [موزیک اینترو (Fade in/out، بعد از گفتار)]
       ↓
[بدنه اصلی: اخبار کانال‌ها — فقط TTS، بدون موسیقی]
       ↓
[متن پایانِ TTS] → [موزیک آوترو (Fade in/out، بعد از گفتار)]
```

- **موسیقی پس‌زمینه نیست**؛ هر بخش موسیقی **مستقل و کامل** بعد از گفتارِ مربوطه پخش می‌شود.
- **Fade ۲ ثانیه‌ای** در ابتدا و انتهای هر فایل موزیک.
- اگر پوشه موزیک خالی باشد، فقط گفتار پخش می‌شود (بدون خطا).
- انتخاب تصادفی: اگر چند فایل در پوشه باشد، هر اجرا یکی به‌صورت تصادفی انتخاب می‌شود.

## دیپلوی (روش پیشنهادی: GitHub Actions)

### ۱. Fork / Clone ریپو
```bash
git clone https://github.com/Bahram-PAB/weekly-podcast-bot.git
cd weekly-podcast-bot
```

### ۲. فایل‌های موزیک (اختیاری)
فایل‌های MP3/WAV/OGG را در دو پوشه قرار دهید:
```
assets/
├── intro_music/   # موزیک אחרי متن آغاز
└── outro_music/   # موزيك بعد از متن پایان
```
اگر فقط یک فایل در هر پوشه باشد، همیشه همان فایل استفاده می‌شود.

### ۳. تنظیم GitHub Secrets
برو به **Settings → Secrets and variables → Actions → New repository secret** و این مقادیر را اضافه کن:

| Secret | توضیح |
|---|---|
| `TELEGRAM_API_ID` | از https://my.telegram.org |
| `TELEGRAM_API_HASH` | از https://my.telegram.org |
| `TELEGRAM_BOT_TOKEN` | از @BotFather |
| `TELEGRAM_CHAT_ID` | آیدی عددی گروه (مثال: `-1001234567890`) |
| `TELEGRAM_SESSION` | StringSession تلگرام (خروجی `create_session.py`) |
| `GEMINI_API_KEY` | از https://aistudio.google.com/apikey |

> **نکته:** Environment tab در تنظیمات ریپو **استفاده نمی‌شود**؛ تمام کلیدها در Secrets ذخیره می‌شوند.

### ۴. اجرا
- **خودکار:** هر یکشنبه ۰۴:۳۰ UTC (= ۰۸:۰۰ تهران) از طریق cron در `.github/workflows/weekly.yml`
- **دستی:** تب **Actions → Weekly Podcast Bot → Run workflow**

### ۵. خروجی
فایل MP3 نهایی در Artifacts اجرا (۷ روز نگهداری) و هم‌زمان در گروه تلگرام ارسال می‌شود.

---

## دیپلوی جایگزین: alwaysdata (Legacy)

> این روش قدیمی است و برای نسخه ۱.۰.۰ تست نشده؛ GitHub Actions روش پیشنهادی است.

### ۱. آپلود فایل‌ها
```bash
sftp [account]@ssh-[account].alwaysdata.net
put -r . /home/[account]/weekly-podcast-bot/
```

### ۲. نصب وابستگی‌ها
```bash
ssh [account]@ssh-[account].alwaysdata.net
cd ~/weekly-podcast-bot
pip3 install --user -r requirements.txt
# ffmpeg باید روی سرور موجود باشد (apt install ffmpeg یا static binary)
```

### ۳. متغیرهای محیطی
در فایل `run.sh` (نه پنل Environment):
```bash
export TELEGRAM_API_ID=...
export TELEGRAM_API_HASH=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export TELEGRAM_SESSION=...
export GEMINI_API_KEY=...
```

### ۴. Cron Task
در پنل ادمین **Advanced → Scheduled Tasks**:
```
Schedule: 30 4 * * 0   # 08:00 Tehran
Command: cd /home/[account]/weekly-podcast-bot && bash run.sh
```

### ۵. user_session.session
فایل `user_session.session` را کپی کنید یا با `create_session.py` بسازید.

---

## ساختار ریپو

```
weekly-podcast-bot/
├── main.py                      # کد اصلی (Telethon + Gemini + pydub + ffmpeg)
├── config.yaml                  # لیست کانال‌ها، تنظیمات گوینده، اصلاح تلفظ
├── requirements.txt             # telethon, google-genai, pydub, pyyaml, jdatetime, requests
├── create_session.py            # تولید StringSession (یک‌بار اجرا)
├── run.sh                       # wrapper برای alwaysdata (اختیاری)
├── assets/
│   ├── intro_music/             # فایل‌های موزیک اینترو
│   └── outro_music/             # فایل‌های موزیک آوترو
├── output/                      # فایل‌های صوتی موقت (gitignore)
└── .github/workflows/
    └── weekly.yml               # GitHub Actions (متد پیشنهادی)
```

## پیش‌نیازها

- Python 3.11+
- ffmpeg در PATH (برای تبدیل WAV→MP3 و خواندن موزیک MP3)
- اکانت تلگرام با دسترسی به کانال‌ها (User API، نه Bot API)
- کلید Gemini API (رایگان در AI Studio)

## کلیدهای API

| کلید | منبع |
|---|---|
| `TELEGRAM_API_ID` | https://my.telegram.org |
| `TELEGRAM_API_HASH` | https://my.telegram.org |
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_CHAT_ID` | آیدی عددی گروه تلگرام |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

## راهنمای عیب‌یابی رایج

| خطا | علت و راه‌حل |
|---|---|
| `Request Entity Too Large (413)` | فایل WAV بزرگ است؛ ffmpeg روی CI نصب شده و در کد فعال است — MP3 ۶۴kbps تولید می‌شود. |
| `ffprobe not found` | ffmpeg در workflow نصب شده (`apt-get install -y ffmpeg`). |
| `TelegramClient has no attribute 'aio'` | در نسخه ۱.۰.۰ اصلاح شد؛ `genai.Client` جدا از `TelegramClient` استفاده می‌شود. |
| `503 UNAVAILABLE` از Gemini | مکانیزم retry در کد وجود دارد (تا ۳ دور، ۵ تلاش در هر دور). |
| موزیک پخش نشد | پوشه `assets/intro_music` یا `assets/outro_music` خالی است — فایل MP3/WAV/OGG قرار دهید. |

## نسخه‌بندی

- **v1.0.0** — اولین نسخه پایدار با ساختار اینترو/اوترو موزیک جداگانه، حذف lameenc، تست‌های خودکار.
- تاریخ: ۱۴۰۵/۰۶/۰۷

## لایسنس

استفاده داخلی پروژه کوهنامه.