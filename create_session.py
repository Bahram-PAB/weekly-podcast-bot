#!/usr/bin/env python3
"""
Create Telethon user session file.
Run this ONCE locally to generate user_session.session.
"""
from telethon.sync import TelegramClient

API_ID = int(input("API ID (from my.telegram.org): "))
API_HASH = input("API Hash: ")
PHONE = input("Phone number (e.g. +98912...): ")

client = TelegramClient("user_session", API_ID, API_HASH)
client.start(phone=PHONE)
print("✅ Session created! user_session.session is ready.")
client.disconnect()
