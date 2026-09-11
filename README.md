# Weekly Podcast Bot

خودکارسازی پادکست هفتگی کوهنامه — انتخاب پربازدیدترین مطالب از کانال‌های تلگرامی و تبدیل به فایل صوتی.

## نحوه کار

```
هر هفته (یکشنبه ۸ صبح)
    │
    ├─ ۱. Telethon → ۷ روز اخبار از ۷۰+ کانال + تعداد بازدید
    ├─ ۲. فیلتر + انتخاب ۲ پست پربازدید هر کانال
    ├─ ۳. Gemini Flash → سناریو تک‌گوینده فارسی
    ├─ ۴. Gemini Live TTS → فایل صوتی WAV
    ├─ ۵. ffmpeg → MP3 (حجم کم)
    ├─ ۶. Bot API → ارسال به گروه تلگرام
    └─ ۷. حذف فایل‌های صوتی
```

## دیپلوی روی alwaysdata (پلن رایگان)

### ۱. آپلود فایل‌ها
```bash
sftp [account]@ssh-[account].alwaysdata.net
put -r . /home/[account]/weekly-podcast-bot/
```

### ۲. نصب dependency
```bash
ssh [account]@ssh-[account].alwaysdata.net
cd ~/weekly-podcast-bot
pip3 install --user -r requirements.txt
```

### ۳. نصب ffmpeg
```bash
# alwaysdata ممکنه ffmpeg نداشته باشه — چک کن
which ffmpeg || apt list --installed 2>/dev/null | grep ffmpeg
# اگر نبود، از ادمین بخواه نصب کنه یا از static binary استفاده کن
```

### ۴. متغیرهای محیطی
از ادمین پنل > **Environment** تنظیم کن:
```
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...
```

### ۵. cron task
از ادمین پنل > **Advanced > Scheduled Tasks**:
```
Schedule: 0 4 * * 0
Command: cd /home/[account]/weekly-podcast-bot && python3 main.py
```

### ۶. user_session.session
فایل `user_session.session` رو از ریپو کپی کن یا با `create_session.py` بساز.

## ساختار

```
weekly-podcast-bot/
├── main.py              # کد اصلی
├── config.yaml          # لیست کانال‌ها، تنظیمات
├── requirements.txt     # dependency ها
├── create_session.py    # ساخت session تلگرام (یکبار اجرا)
└── .github/workflows/
    └── weekly.yml       # GitHub Actions (جایگزین alwaysdata cron)
```

## API Keys

| Key | منبع |
|---|---|
| TELEGRAM_API_ID | https://my.telegram.org |
| TELEGRAM_API_HASH | https://my.telegram.org |
| TELEGRAM_BOT_TOKEN | @BotFather |
| TELEGRAM_CHAT_ID | آی‌دی گروه تلگرام |
| GEMINI_API_KEY | https://aistudio.google.com/apikey |
