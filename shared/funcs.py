import discord
import os
import io
import re
import sys
import json
import asyncio
import datetime
import concurrent.futures
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import Content, Part


# モジュール読み込みパス追加
sys.path.append('/app/shared')
import config

# グローバル変数
bot_client = None
GEMINI_TOKEN = None
model_name = "gemini-2.0-flash"  # 使用するAIモデル名
message_buffer_per_ch = {}  # チャンネルごとのメッセージバッファ
is_responding_per_ch = {}  # チャンネルごとのAI応答状態
message_locks_per_ch = {}  # チャンネルごとのロック
executor = concurrent.futures.ThreadPoolExecutor()  # 非同期実行のためのスレッドプール
lastmessage_metadata = None

# 非同期ロックを取得するためのヘルパー関数
def get_lock(guild_id, channel_id):
    return message_locks_per_ch.setdefault(guild_id, {}).setdefault(channel_id, asyncio.Lock())

# 同期関数を非同期に実行するためのヘルパー関数
def run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(executor, func, *args)

# 設定された応答チャンネルをリスト表示
async def list_channel(message):
    guild_id = str(message.guild.id)

    if guild_id not in config.allowed_channels_per_guild or not config.allowed_channels_per_guild[guild_id]:
        await message.channel.send("!このサーバーには応答チャンネルが設定されていません。")
        return

    # チャンネル一覧の作成
    channel_mentions = []
    for ch_id in config.allowed_channels_per_guild[guild_id]:
        ch = message.guild.get_channel(ch_id)
        if ch:
            channel_mentions.append(f"<#{ch_id}>")
        else:
            channel_mentions.append(f"`{ch_id}`（見つかりません）")

    # チャンネル情報の送信
    channels_text = "\n".join(channel_mentions)
    await message.channel.send(f"!現在設定されている応答チャンネル一覧:\n{channels_text}")

# 設定ファイルを送信する関数
async def send_config(message, config_path):
    if not os.path.exists(config_path):
        await message.channel.send("!設定ファイルが存在しません。")
        return
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        filename = f"{message.guild.id}_{message.channel.id}_config.txt"
        file = discord.File(io.BytesIO(content.encode()), filename)
        await message.channel.send("!設定ファイルを送信します。", file=file)
    except Exception as e:
        print(f"[send_config] エラー: {e}")
        await message.channel.send("!設定ファイルの送信に失敗しました。")

# 設定ファイルをリセットする関数
async def reset_config(message, config_path):
    await send_config(message, config_path)
    try:
        os.remove(config_path)
        await message.channel.send("!設定ファイルを削除しました。")
    except Exception as e:
        print(f"[reset_config] エラー: {e}")
        await message.channel.send("!設定ファイルの削除に失敗しました。")

# チャット履歴をJSON形式に変換する関数
def convert_chat_history_to_json(chat):
    def content_to_dict(content):
        parts_text_only = []
        for part in content.parts:
            if hasattr(part, "text"):
                parts_text_only.append(part.text)
            else:
                parts_text_only.append(str(part))  # 保険的に他の型も文字列化
        return {"role": content.role, "parts": parts_text_only}
    return [content_to_dict(c) for c in chat.get_history(curated=True)]


# チャット履歴をメッセージとして送信
async def send_history(message, chat):
    history_json = convert_chat_history_to_json(chat)
    filename = f"chat_history_{message.guild.id}_{message.channel.id}.json"

    try:
        # JSON形式の履歴ファイルを送信
        file = discord.File(io.BytesIO(json.dumps(history_json, ensure_ascii=False, separators=(',', ':')).encode()), filename)
        await message.channel.send("!チャット履歴ファイルを送信します。", file=file)
    except Exception as e:
        print(f"[send_chat_history] エラー: {e}")
        await message.channel.send("!チャット履歴の送信に失敗しました。")

# チャット履歴を指定したディレクトリに保存
def save_chat(chat, config_path, guild_id, save_dir, name="!chatdata"):
    # ギルドディレクトリの作成
    guild_dir = os.path.join(save_dir, f"{guild_id}")
    os.makedirs(guild_dir, exist_ok=True)
    
    # 名前とタイムスタンプの作成
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{name}_{timestamp}"
    save_path = os.path.join(guild_dir, f"{base_name}")
    os.makedirs(save_path, exist_ok=True)
    
    # JSONファイルの保存
    history_json = convert_chat_history_to_json(chat)
    with open(os.path.join(save_path, f"history_{base_name}.json"), "w", encoding="utf-8") as f:
        json.dump(history_json, f, ensure_ascii=False, separators=(',', ':'))
    
    # 設定ファイルの保存
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as src, \
             open(os.path.join(save_path, f"config_{base_name}.txt"), "w", encoding="utf-8") as dst:
            dst.write(src.read())
    
    # READMEファイルの保存
    with open(os.path.join(save_path, f"readme_{base_name}.txt"), "w", encoding="utf-8") as f:
        f.write("試験的に保存されたチャット履歴です。")
    
    print(f"チャット履歴が保存されました: {base_name}")
    return base_name

# チャット履歴一覧を表示
async def list_chat(message):
    guild_id = str(message.guild.id)
    guild_dir = f"/app/shared/saved_chat/{guild_id}"
    
    # ギルドディレクトリが存在しない場合
    if not os.path.exists(guild_dir):
        await message.channel.send("!保存されたチャット履歴はありません。")
        return

    # ギルドディレクトリ内の保存されたチャットを検索
    saved_chats = []
    for subdir in os.listdir(guild_dir):
        subdir_path = os.path.join(guild_dir, subdir)
        if os.path.isdir(subdir_path):
            # readmeファイルの読み込み
            readme_path = os.path.join(subdir_path, f"readme_{subdir}.txt")
            if os.path.exists(readme_path):
                with open(readme_path, "r", encoding="utf-8") as f:
                    description = f.read().strip()
            else:
                description = "説明がありません。"

            # 保存されたチャットの情報をリストに追加
            saved_chats.append({
                "name": subdir,
                "description": description
            })
    
    # チャット履歴が存在する場合
    if saved_chats:
        chat_list_text = "\n".join([f"**{chat['name']}**: {chat['description']}" for chat in saved_chats])
        await message.channel.send(f"!保存されたチャット履歴一覧:\n{chat_list_text}")
    else:
        await message.channel.send("!保存されたチャット履歴はありません。")

def load_chat(guild_id, chat_dir, channel_id, ch_config_path):
    # チャット履歴ファイルのパス
    load_history_path = f"/app/shared/saved_chat/{guild_id}/{chat_dir}/history_{chat_dir}.json"
    # 設定ファイルのパス
    load_config_path = f"/app/shared/saved_chat/{guild_id}/{chat_dir}/config_{chat_dir}.txt"

    # 履歴ファイルが存在しない場合はエラー
    if not os.path.exists(load_history_path):
        return None

    # チャット履歴の読み込み
    with open(load_history_path, "r", encoding="utf-8") as f:
        history_dicts = json.load(f)
    
    history = [
        Content(
            role=item["role"],
            parts=[
                Part(text=p) if isinstance(p, str) else Part(**p)
                for p in item["parts"]
            ]
        )
        for item in history_dicts
    ]

    # 設定ファイルの読み込み
    inst = ""
    if os.path.exists(load_config_path):
        with open(load_config_path, "r", encoding="utf-8") as f:
            inst = f.read()

    # 設定ファイルを`chat_config` で上書き
    os.makedirs(os.path.dirname(ch_config_path), exist_ok=True)
    with open(ch_config_path, "w", encoding="utf-8") as f:
        f.write(inst)

    # チャットオブジェクトを作成して返す
    client = genai.Client(api_key=GEMINI_TOKEN)
    chat = client.chats.create(
        model=model_name,
        history=history,
        config=types.GenerateContentConfig(system_instruction=inst)
    )

    return chat

# 最後に記憶しているメッセージを送信する関数
async def send_last_message(message, chat):
    history = chat.get_history(curated=True)
    if not history:
        await message.channel.send("!履歴が空です。")
        return

    last = history[-1]
    role = last.role
    parts = [part.text for part in last.parts if hasattr(part, "text")]
    text = "\n".join(parts) if parts else "(内容なし)"

    await message.channel.send(f"!最後のメッセージ:\n**{role}**: {text}")

# チャット履歴を復元する関数
def restore_chat(filepath, config_path):
    # チャット履歴の復元
    with open(filepath, "r", encoding="utf-8") as f:
        history_dicts = json.load(f)
    history = [Content(role=item["role"], parts=[Part(**p) for p in item["parts"]]) for item in history_dicts]

    # 設定ファイルの復元
    inst = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                inst = f.read()
        except Exception as e:
            print(f"[restore_chat] 設定ファイルの読み込みエラー: {e}")
            inst = ""

    # チャットオブジェクトの復元
    client = genai.Client(api_key=GEMINI_TOKEN)
    return client.chats.create(
        model=model_name,
        history=history,
        config=types.GenerateContentConfig(system_instruction=inst)
    )



# 初期化関数
def ready(client, token):
    global bot_client, GEMINI_TOKEN
    bot_client, GEMINI_TOKEN = client, token



# =====メッセージ処理を行うメイン関数=====

async def handle_message(message, allowed_channels_per_guild, chats_per_ch):
    global lastmessage_metadata
    if message.author == bot_client.user or not message.guild:
        return

    guild_id, channel_id = str(message.guild.id), message.channel.id
    config_path = f"/app/bot/chat_config/chat_config_{guild_id}/chat_config_{channel_id}.txt"
    chat = chats_per_ch.get(guild_id, {}).get(channel_id)

    # 許可されたチャンネルでない場合は処理をスキップ
    if channel_id not in allowed_channels_per_guild.get(guild_id, set()):
        return

    # メッセージ内容の整形
    content = message.content.replace("\n", "\\n").replace("\r", "\\r")
    mention_1 = f"<@{bot_client.user.id}>"
    mention_2 = f"<@!{bot_client.user.id}>"

    if content.startswith(mention_1):
        content = content[len(mention_1):].strip()
    elif content.startswith(mention_2):
        content = content[len(mention_2):].strip()

    # "!"で始まるコマンドはAIに送信せず処理
    if content.startswith("!"):
        if bot_client.user in message.mentions:
            if content == "!check":
                await message.channel.send("!このチャンネルを見ています")
                return

            if content == "!list_channel":
                await list_channel(message)
                return
            if content == "!send_config":
                await send_config(message, config_path)
                return

            if content == "!reset_config":
                await reset_config(message, config_path)
                return

            if content == "!send_history":
                # チャット履歴がない場合はエラーメッセージ
                if chat is None:
                    await message.channel.send("!チャット履歴が見つかりません。")
                    return

                await send_history(message, chat)
                return

            if content == "!reset_chat":
                # チャット履歴をリセットする処理
                if guild_id in chats_per_ch and channel_id in chats_per_ch[guild_id]:
                    chat_history = chats_per_ch[guild_id][channel_id]

                    # チャット履歴を送信
                    await send_history(message, chat_history)

                    # チャット履歴をリセット
                    await reset_config(message, config_path)
                    del chats_per_ch[guild_id][channel_id]
                    message_buffer_per_ch[guild_id][channel_id] = []

                    await message.channel.send("!チャット履歴がリセットされました。")
                else:
                    await message.channel.send("!リセットするチャット履歴が見つかりません。")
                return

            if content == "!save_chat":
                # チャット履歴を保存する処理
                if guild_id in chats_per_ch and channel_id in chats_per_ch[guild_id]:
                    chat_history = chats_per_ch[guild_id][channel_id]

                    # チャット履歴をリセット
                    saved_name = save_chat(chat_history, config_path, guild_id, "/app/shared/saved_chat")
                    await message.channel.send("!チャット履歴が保存されました。")
                    await message.channel.send(f"{saved_name}")
                else:
                    await message.channel.send("!保存するチャット履歴が見つかりません。")
                return

            if content == "!list_chat":
                # 保存ディレクトリを指定して履歴一覧を表示
                await list_chat(message)
                return

            if content.startswith("!load_chat "):
                parts = content.split(" ", 1)
                if len(parts) == 2:
                    chat_dir = parts[1].strip()

                    # 現在のチャット履歴が存在する場合は事前に送信
                    if guild_id in chats_per_ch and channel_id in chats_per_ch[guild_id]:
                        current_chat = chats_per_ch[guild_id][channel_id]
                        await send_history(message, current_chat)
                        await send_config(message, config_path)
                    # チャット履歴と設定をロード
                    ch_config_path = f"/app/bot/chat_config/chat_config_{guild_id}/chat_config_{channel_id}.txt"

                    chat = load_chat(guild_id, chat_dir, channel_id, ch_config_path)
                    if chat is None:
                        await message.channel.send("!指定した履歴ファイルが見つかりません。")
                        return
                    # チャットオブジェクトを保存
                    chats_per_ch.setdefault(guild_id, {})[channel_id] = chat
                    await message.channel.send(f"!チャット履歴と設定を{chat_dir}から復元しました。")
                else:
                    await message.channel.send("!使い方: `!load_chat saved_chat_<名前>_<日時>`")
                return


            if content == "!send_buffered":
                buffered = message_buffer_per_ch[guild_id][channel_id]
                if not buffered:
                    await message.channel.send("!バッファ内容はありません。")
                    return
                try:
                    await message.channel.send(f"!バッファ内容:\n{buffered}")
                except Exception as e:
                    print(f"[flush_message_buffer] 送信エラー: {e}")

            if content == "!reset_buffered":
                message_buffer_per_ch[guild_id][channel_id] = []
                await message.channel.send("!バッファ内容を削除しました。")
                return

            if content == "!send_last":
                if not chat:
                    await message.channel.send("!チャット履歴がありません。")
                    return
                await send_last_message(message, chat)
                return
                
            if content == "!send_lastdata":
                if not lastmessage_metadata:
                    await message.channel.send("!送信履歴はありません。")
                    return
                try:
                    await message.channel.send(f"!最後に送信されたチャットのメタデータ:\n{lastmessage_metadata}")
                except Exception as e:
                    print(f"[flush_message_buffer] 送信エラー: {e}")
            
            else:
                await message.channel.send("!登録されていない!コマンドです。")
        return

    # 自分以外へのコマンド命令を無視
    mention_pattern = r"^<@!?(?P<id>\d+)>"

    match_mention = re.match(mention_pattern, content)
    if match_mention:
        mentioned_id = match_mention.group("id")
        remaining = content[match_mention.end():].strip()
        if remaining.startswith("!"):
            return
        content = remaining

    # メッセージ整形と指示抽出
    matches = re.findall(r'【(.*?)】', content, re.DOTALL)
    if matches:
        if bot_client.user in message.mentions:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            try:
                with open(config_path, 'a', encoding='utf-8') as f:
                    f.writelines(match + '\n' for match in matches)
            except Exception as e:
                print(f"[config write] エラー: {e}")
        for match in matches:
            content = content.replace(f"【{match}】", "")

    authorname = message.author.display_name
    modified = f"{authorname}: {content}" if content.strip() else ""

    # 返信状態とメッセージ格納の初期設定
    is_responding_per_ch.setdefault(guild_id, {}).setdefault(channel_id, False)
    message_buffer_per_ch.setdefault(guild_id, {}).setdefault(channel_id, [])
    if bot_client.user not in message.mentions or is_responding_per_ch[guild_id][channel_id]:
        lock = get_lock(guild_id, channel_id)
        async with lock:
            message_buffer_per_ch[guild_id][channel_id].append(f"{modified},\n")
        return

    # AIによる応答処理
    is_responding_per_ch[guild_id][channel_id] = True
    lock = get_lock(guild_id, channel_id)
    async with lock:
        if message.author.bot:
            await asyncio.sleep(5)

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        if not os.path.exists(config_path):
            open(config_path, 'w').close()

        with open(config_path, 'r', encoding='utf-8') as f:
            inst = f.read()

        chats_per_ch.setdefault(guild_id, {})
        if channel_id not in chats_per_ch[guild_id]:
            client = genai.Client(api_key=GEMINI_TOKEN)
            chats_per_ch[guild_id][channel_id] = client.chats.create(
                model=model_name,
                config=types.GenerateContentConfig(system_instruction=inst)
            )

        chat = chats_per_ch[guild_id][channel_id]
        buffered = message_buffer_per_ch[guild_id][channel_id]
        input_text = ",\r\n".join(buffered + [modified])

    async with message.channel.typing():
        try:
            response = await run_blocking(chat.send_message, input_text, types.GenerateContentConfig(system_instruction=inst))
            lastmessage_metadata = message.channel.send(response.usage_metadata)
            await message.channel.send(response.text)
            async with lock:
                message_buffer_per_ch[guild_id][channel_id] = []
        except Exception as e:
            print(f"応答エラー: {e}")
            await message.channel.send("!エラーが発生しました。時間を置いて再試行してください。")
        finally:
            is_responding_per_ch[guild_id][channel_id] = False
