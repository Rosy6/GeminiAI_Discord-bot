import json
import os
from dotenv import load_dotenv

CHANNEL_FILE = "allowed_channels.json"
allowed_channels_per_guild = {}
# トークン（.env から読み込み）
GEMINI_TOKEN = None
DISCORD_TOKEN = None

def load_env(env_path="/app/.env"):
    """環境変数を読み込む（GEMINI_TOKEN と DISCORD_TOKEN を取得）"""
    global GEMINI_TOKEN, DISCORD_TOKEN
    load_dotenv(env_path)
    GEMINI_TOKEN = os.getenv("GEMINI_TOKEN")
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

def save_allowed_channels():
    with open(CHANNEL_FILE, "w") as f:
        json.dump(allowed_channels_per_guild, f)

def load_allowed_channels():
    global allowed_channels_per_guild
    if os.path.exists(CHANNEL_FILE):
        with open(CHANNEL_FILE, "r") as f:
            allowed_channels_per_guild = json.load(f)
    else:
        allowed_channels_per_guild = {}
