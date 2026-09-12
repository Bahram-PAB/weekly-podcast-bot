#!/usr/bin/env python3
"""
Weekly Podcast Bot
Reads Telegram channels via Telethon, selects top posts by views,
generates single-presenter podcast script + audio via Gemini.
Deploy: alwaysdata Free plan.
"""

import asyncio
import io
import json
import os
import re
import wave
import yaml
import logging
import requests
from datetime import datetime, timedelta
import jdatetime
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
TEXT_MODEL = "gemini-3.6-flash"
SAMPLE_RATE = 24000
VOICE = "Charon"  # Informative male


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# =============================================================================
# Fetch messages from a single channel (last 7 days, with views)
# =============================================================================

async def fetch_messages_from_channel(client, channel_username, since_date):
    from telethon import errors
    messages = []
    try:
        entity = await client.get_entity(channel_username)
        async for message in client.iter_messages(entity, limit=300):
            if message.date.replace(tzinfo=None) >= since_date:
                text = message.text or ""
                messages.append({
                    "id": message.id,
                    "date": message.date.isoformat(),
                    "text": text,
                    "views": message.views or 0,
                    "has_media": message.media is not None,
                    "has_text": len(text.strip()) > 20,
                    "channel": channel_username,
                })
            else:
                break
    except errors.UsernameNotOccupiedError:
        logger.warning(f"Channel not found: @{channel_username}")
    except errors.ChannelPrivateError:
        logger.warning(f"Channel is private: @{channel_username}")
    except errors.FloodWaitError as e:
        if e.seconds > 300:
            logger.warning(f"Flood wait {e.seconds}s too long for @{channel_username}, skipping")
            return messages
        logger.warning(f"Flood wait for @{channel_username}: {e.seconds}s")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error fetching @{channel_username}: {e}")
    return messages


# =============================================================================
# Filter + Select top posts per channel
# =============================================================================

def select_top_posts(messages, config):
    """Filter messages then pick top N by views per channel."""
    filters = config.get("filters", {})
    exclude_keywords = filters.get("exclude_keywords", [])
    min_caption_length = filters.get("min_caption_length", 50)
    min_views = filters.get("min_views", 10)
    top_n = filters.get("top_posts_per_channel", 2)
    priority_channels = set(config.get("priority_channels", []))

    # Step 1: basic filtering
    filtered = []
    seen_texts = set()
    for msg in messages:
        channel = msg.get("channel", "")
        is_priority = f"@{channel}" in priority_channels
        text = msg.get("text", "").strip()
        if not text or len(text) < min_caption_length:
            continue
        if not is_priority:
            if any(kw in text for kw in exclude_keywords):
                continue
            if msg.get("has_media") and not msg.get("has_text"):
                continue
        key = text[:100]
        if key in seen_texts:
            continue
        seen_texts.add(key)
        filtered.append(msg)

    # Step 2: group by channel, sort by views, take top N
    by_channel = {}
    for msg in filtered:
        ch = msg["channel"]
        by_channel.setdefault(ch, []).append(msg)

    selected = []
    active_channels = 0
    for ch, msgs in by_channel.items():
        is_priority = f"@{ch}" in priority_channels
        # Sort by views descending
        msgs.sort(key=lambda m: m.get("views", 0), reverse=True)
        # Priority channels: always at least 1 post even if low views
        if is_priority:
            active_channels += 1
            selected.extend(msgs[:top_n])
        else:
            # Non-priority: only if meets min views
            good = [m for m in msgs if m.get("views", 0) >= min_views]
            if good:
                active_channels += 1
                selected.extend(good[:top_n])

    logger.info(f"Filtered {len(messages)} -> {len(filtered)} -> selected {len(selected)} top posts from {active_channels} channels")
    return selected, active_channels


# =============================================================================
# Build source text for single-presenter script
# =============================================================================

def build_source_text(selected_posts, channel_names=None, active_channels=0):
    today_jalali = jdatetime.datetime.now()
    week_ago_jalali = today_jalali - jdatetime.timedelta(days=7)
    names = channel_names or {}

    total_views = sum(p.get("views", 0) for p in selected_posts)

    text_parts = [
        f"آمار هفتگی: {len(selected_posts)} مطلب منتخب از {active_channels} کانال فعال، مجموع بازدید: {total_views:,}.",
        "",
    ]

    # Group selected posts by channel for organized output
    by_channel = {}
    for p in selected_posts:
        by_channel.setdefault(p["channel"], []).append(p)

    for ch_name, posts in by_channel.items():
        friendly = names.get(f"@{ch_name}", ch_name)
        text_parts.append(f"\nکانال {friendly}:")
        for p in posts:
            views = p.get("views", 0)
            text_parts.append(f"- [بازدید: {views:,}] {p['text'][:600]}")

    source_text = "\n".join(text_parts)
    date_range = f"{week_ago_jalali.day} {JALALI_MONTHS[week_ago_jalali.month - 1]} تا {today_jalali.day} {JALALI_MONTHS[today_jalali.month - 1]} {today_jalali.year}"
    podcast_date = f"{today_jalali.day} {JALALI_MONTHS[today_jalali.month - 1]} {today_jalali.year}"

    return source_text, date_range, podcast_date, len(selected_posts), active_channels


# =============================================================================
# Generate podcast script — single presenter monologue
# =============================================================================

async def generate_podcast_script(source_text, date_range, podcast_date, speaker_name):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set!")
        return None

    client = genai.Client(api_key=api_key)

    prompt = f"""
# نقش
تو نویسنده‌ی حرفه‌ای پادکست تک‌گوینده هستی. محتوا را به صورت یک گفتار رادیویی روان و طبیعی توسط یک گوینده‌ی مرد می‌نویسی.

# ورودی
متن زیر شامل منتخب پربازدیدترین مطالب کانال‌های تلگرامی کوهنوردی در هفته گذشته ({date_range}) است.
هر کانال حداکثر ۲ مطلب پربازدید دارد.

متن اخبار:
{source_text}

# گوینده
{speaker_name}

# لحن
گرم، صمیمی، روان، مثل یک مجری تک‌نفره‌ی پادکست صبحگاهی. طبیعی صحبت کن، نه مثل متن نوشته‌شده.
گاهی از عبارات انتقالی متنوع استفاده کن (مثلاً «یه خبر دیگه که این هفته جلب توجه کرد...»، «نکته جالب اینجاست که...»، «و اما مطلب بعدی...»).
از تکرار عبارات انتقالی در طول برنامه خودداری کن.

# ساختار خروجی

## آغاز (دقیقاً همین متن)
{speaker_name}: سلام و درود خدمت شنوندگان عزیز پادکست کوهنامه. امروز {podcast_date} هست و با یه خلاصه هفتگی از پربازدیدترین مطالب کانال‌های تلگرامی کوهنوردی در خدمتتون هستیم. {date_range} رو با هم مرور می‌کنیم.

## بدنه
برای هر خبر:
۱. خبر را با کلمات خودت شروع کن (کپی مستقیم از منبع نکن).
۲. ۲-۳ جمله جزئیات بده (چه اتفاقی افتاده، چه کسی، چرا مهم است).
۳. اگر نکته تحلیلی یا مقایسه‌ای هست، ۱-۲ جمله اضافه کن.
۴. با عبارتی متفاوت به خبر بعدی برو.

قوانین محتوا:
- مطالب هر کانال را پشت سر هم بیار (گروه‌بندی بر اساس کانال).
- بازدید هر مطلب رو به صورت طبیعی بگو (مثلاً «این پست بیشتر از ۵۰۰۰ بازدید داشته»).
- اگر مطلبی کوتاه یا ساده است، در ۱-۲ جمله رد شو.
- کل پادکست بین ۵ تا ۱۰ دقیقه باشد (بسته به تعداد مطالب).

## پایان (دقیقاً همین متن)
{speaker_name}: این بود خلاصه‌ی پربازدیدترین مطالب هفتگی کانال‌های کوهنوردی. امیدوارم براتون مفید بوده باشه. پادکست‌های ما رو با دوستان کوهنوردتون به اشتراک بگذارید و منتظر پادکست هفتگی بعدی باشید. تا دفعه بعد، خدا نگهدارتون باشه.

# قوانین خروجی
- فقط و فقط دیالوگ خروجی بده؛ هیچ توضیح، عنوان، یادداشت یا خلاصه اضافی ننویس.
- هیچ نشانه‌ی مارک‌داون (ستاره، هشتگ، خط تیره، براکت) در خروجی نباشد.
- هر خط دقیقاً با این فرمت شروع شود:
{speaker_name}: ...
- از متن منبع کپی مستقیم نکن؛ همه‌چیز را با زبان طبیعی گفتاری بازنویسی کن.
"""

    MAX_ROUNDS = 3
    ROUND_WAIT = 300  # 5 min between rounds (not 1 hour)

    for round_num in range(MAX_ROUNDS):
        if round_num > 0:
            logger.warning(f"All 5 attempts failed. Waiting {ROUND_WAIT}s before round {round_num+1}...")
            await asyncio.sleep(ROUND_WAIT)

        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model=TEXT_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=f"تو یک نویسنده پادکست تک‌گوینده حرفه‌ای فارسی هستی. نام گوینده: {speaker_name}.",
                        temperature=0.7,
                    ),
                )
                script = response.text
                logger.info(f"Script generated: {len(script)} chars, {len(script.splitlines())} lines")
                return script
            except Exception as e:
                wait = 30 + (30 * attempt)  # 30, 60, 90, 120, 150 seconds
                logger.warning(f"Script attempt {attempt+1}/5 (round {round_num+1}) failed: {type(e).__name__}: {e}. Retry in {wait}s...")
                await asyncio.sleep(wait)

    logger.error("Script generation failed after all rounds!")
    return None


# =============================================================================
# Render to audio via Gemini Live API (single voice)
# =============================================================================

async def render_podcast_audio(script, output_wav, speaker_name, voice, corrections=None):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set!")
        return False

    lines = [l.strip() for l in script.strip().split("\n") if l.strip()]
    turns = []
    for line in lines:
        match = re.match(rf"^{re.escape(speaker_name)}\s*:\s*(.*)", line)
        if not match:
            continue
        text = match.group(1)
        if corrections:
            for wrong, right in sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True):
                text = text.replace(wrong, right)
        turns.append(text)

    logger.info(f"Rendering {len(turns)} turns via Gemini Live API...")
    all_pcm = bytearray()

    for i, text in enumerate(turns):
        logger.info(f"Turn {i+1}/{len(turns)}: {text[:60]}...")
        try:
            client = genai.Client(api_key=api_key)
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                output_audio_transcription=types.AudioTranscriptionConfig(),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
                system_instruction=(
                    f"You are {speaker_name}. Speak in natural contemporary Iranian Persian. "
                    "Deliver the text as warm, natural human speech. "
                    "Say each sentence once at a comfortable pace."
                ),
                temperature=0.7,
            )

            async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
                prompt = (
                    "Perform only the exact text inside <READ>. Preserve every word, but deliver "
                    "it as warm, natural human speech with varied emphasis, comfortable phrasing, "
                    "and unhurried articulation. Say each sentence once. Stop immediately after the "
                    f"final word and produce only audible speech.\n\n<READ>\n{text}\n</READ>"
                )
                await session.send_client_content(
                    turns=[{"role": "user", "parts": [{"text": prompt}]}]
                )

                pcm = bytearray()
                async for message in session.receive():
                    server_content = getattr(message, "server_content", None)
                    model_turn = getattr(server_content, "model_turn", None) if server_content else None
                    for part in getattr(model_turn, "parts", None) or []:
                        inline = getattr(part, "inline_data", None)
                        data = getattr(inline, "data", None) if inline else None
                        if data:
                            pcm.extend(data)
                    if not pcm and getattr(message, "data", None):
                        pcm.extend(message.data)
                    if server_content and (
                        getattr(server_content, "turn_complete", False)
                        or getattr(server_content, "generation_complete", False)
                    ):
                        break

                if pcm:
                    all_pcm.extend(pcm)
                    logger.info(f"  Got {len(pcm)} bytes PCM ({len(pcm)/(SAMPLE_RATE*2):.1f}s)")
                else:
                    logger.warning(f"  No audio for turn {i+1}")

        except Exception as e:
            logger.error(f"Error on turn {i+1}: {e}")
            continue

        await asyncio.sleep(1)

    if not all_pcm:
        logger.error("No audio generated!")
        return False

    # Write WAV
    with wave.open(output_wav, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(all_pcm))

    wav_duration = len(all_pcm) / (SAMPLE_RATE * 2)
    logger.info(f"WAV saved: {output_wav} ({wav_duration:.1f}s)")
    return True


# =============================================================================
# WAV -> MP3 conversion (ffmpeg)
# =============================================================================

def wav_to_mp3(wav_path, mp3_path, bitrate=64):
    """WAV -> MP3 using lameenc (pure Python, no ffmpeg needed)."""
    import lameenc
    try:
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(bitrate)
        encoder.set_num_channels(1)
        encoder.set_in_sample_rate(SAMPLE_RATE)
        encoder.set_out_sample_rate(SAMPLE_RATE)

        mp3_frames = bytearray()
        with wave.open(wav_path, "rb") as wav:
            chunk_size = 1152  # LAME works in 1152-sample frames
            while True:
                frames = wav.readframes(chunk_size)
                if not frames:
                    break
                # lameenc expects bytes, returns encoded bytes
                encoded = encoder.encode(frames)
                mp3_frames.extend(encoded)
            # Flush remaining
            remaining = encoder.flush()
            mp3_frames.extend(remaining)

        with open(mp3_path, "wb") as f:
            f.write(mp3_frames)

        mp3_size = os.path.getsize(mp3_path) / (1024 * 1024)
        logger.info(f"MP3 saved: {mp3_path} ({mp3_size:.1f}MB)")
        return True
    except Exception as e:
        logger.error(f"MP3 conversion failed: {e}")
        return False


# =============================================================================
# Send to Telegram
# =============================================================================

def send_to_telegram(audio_path, title, caption):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not set")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
    with open(audio_path, "rb") as audio:
        resp = requests.post(url,
            files={"audio": audio},
            data={"chat_id": chat_id, "caption": caption[:1024], "title": title, "performer": "کوهنامه"},
            timeout=120,
        )
        if resp.status_code == 200:
            logger.info("Audio sent to Telegram successfully")
            return True
        logger.error(f"Telegram error: {resp.text}")
        return False


# =============================================================================
# Main
# =============================================================================

async def async_main():
    config = load_config()
    channels = config.get("channels", [])
    speaker_cfg = config.get("speaker", {})
    speaker_name = speaker_cfg.get("name", "فرشید")
    speaker_voice = speaker_cfg.get("voice", "Charon")

    if not channels:
        logger.error("No channels configured!")
        return

    api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID or TELEGRAM_API_HASH not set!")
        return

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    session_str = os.environ.get("TELEGRAM_SESSION", "")
    if session_str:
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
    else:
        client = TelegramClient("user_session", api_id, api_hash)
    await client.start()
    try:
        # Step 1: Fetch messages from last 7 days
        since_date = datetime.utcnow() - timedelta(days=7)
        logger.info(f"Fetching messages from {len(channels)} channels (last 7 days)...")
        messages = []
        for ch in channels:
            username = ch.lstrip("@") if isinstance(ch, str) else ch.get("username", "").lstrip("@")
            msgs = await fetch_messages_from_channel(client, username, since_date)
            messages.extend(msgs)
            await asyncio.sleep(2)
        await client.disconnect()
        logger.info(f"Total messages fetched: {len(messages)}")

        if not messages:
            logger.warning("No messages found. Nothing to podcast.")
            return

        # Step 2: Select top posts by views
        selected, active_channels = select_top_posts(messages, config)
        if not selected:
            logger.warning("No posts selected after filtering.")
            return

        # Step 3: Build source text
        source_text, date_range, podcast_date, total_posts, _ = build_source_text(
            selected, channel_names=config.get("channel_names", {}), active_channels=active_channels
        )
        logger.info(f"Source: {total_posts} posts from {active_channels} channels, range={date_range}")

        # Step 4: Generate script
        logger.info("Generating podcast script...")
        script = await generate_podcast_script(source_text, date_range, podcast_date, speaker_name)
        if not script:
            logger.error("Script generation failed!")
            return

        # Step 5: Render audio
        os.makedirs("output", exist_ok=True)
        date_slug = podcast_date.replace(" ", "_")
        wav_path = f"output/podcast_{date_slug}.wav"
        mp3_path = f"output/podcast_{date_slug}.mp3"

        logger.info("Rendering podcast audio...")
        success = await render_podcast_audio(script, wav_path, speaker_name, speaker_voice,
            corrections=config.get("pronunciation_corrections", {}))
        if not success:
            logger.error("Audio generation failed!")
            return

        # Step 6: WAV -> MP3
        if not wav_to_mp3(wav_path, mp3_path):
            logger.error("MP3 conversion failed!")
            return

        # Step 7: Send to Telegram
        logger.info("Sending to Telegram...")
        title = f"پادکست هفتگی کوهنامه {podcast_date}"
        caption = (
            f"🎙 پادکست هفتگی {podcast_date}\n"
            f"精选 پربازدیدترین مطالب کانال‌های کوهنوردی ({date_range})\n"
            f"📤 تهیه شده توسط هوش مصنوعی\n"
            f"────────────\n"
            f"🌐 کوهنامه | پادکست کوهنوردی\n"
            f"📍 www.koohnameh.ir\n"
            f"📢 @koohnameh"
        )
        send_to_telegram(mp3_path, title, caption)

        # Step 8: Cleanup — delete audio files
        for f in [wav_path, mp3_path]:
            if os.path.exists(f):
                os.remove(f)
                logger.info(f"Deleted: {f}")

        logger.info("Done!")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await client.disconnect()
        except Exception:
            pass


def main():
    logger.info("Starting Weekly Podcast Bot...")
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
