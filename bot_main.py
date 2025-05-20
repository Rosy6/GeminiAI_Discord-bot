import discord
import os
import sys
import importlib

# モジュール読み込みパス追加
sys.path.append('/app/shared')
import commands
import config
import funcs

chats_per_ch = {}

# 起動・トークンを.envから取得
config.load_env()
GEMINI_TOKEN = config.GEMINI_TOKEN
DISCORD_TOKEN = config.DISCORD_TOKEN

# 接続オブジェクト
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
# コマンドツリー初期化
tree = discord.app_commands.CommandTree(client)

# モジュール初期化
async def initialize_bot():
    global client

    # モジュール再読み込み
    importlib.reload(funcs)
    importlib.reload(commands)
    importlib.reload(config)

    # コンフィグ
    config.load_allowed_channels()
    commands.reloadconfig()
    funcs.ready(client, GEMINI_TOKEN)
    # コマンド一覧を確認
    try:
        # グローバルコマンドを取得
        global_commands = await tree.fetch_commands()
        print("登録されているグローバルコマンド一覧:")
        if not global_commands:
            print("  登録されているグローバルコマンドはありません")
        for command in global_commands:
            print(f" - {command.name}")
    except Exception as e:
        print(f"グローバルコマンドの取得に失敗: {e}")
    # guild command
    for guild in client.guilds:
        commands_list = await tree.fetch_commands(guild=guild)
        print(f"{guild.name} のコマンド一覧:")
        if not commands_list:
            print("  登録されているコマンドはありません")
        for command in commands_list:
            print(f" - {command.name}")

# /reload_modules コマンド定義
@tree.command(name="reload_modules", description="モジュールをリロードします")
@discord.app_commands.checks.has_permissions(administrator=True)
async def reload_modules(interaction: discord.Interaction):
    await initialize_bot()
    await interaction.response.send_message("モジュールをリロードしました", ephemeral=True)

# 起動時イベント
@client.event
async def on_ready():
    await initialize_bot()
    commands.setup(tree)

    # グローバルコマンドの同期
    try:
        await tree.sync(guild=None)  # これでグローバルコマンドがすべてのギルドに反映されます
        print("グローバルコマンドを同期しました")
    except Exception as e:
        print(f"グローバルコマンドの同期に失敗: {e}")

    for guild in client.guilds:
        try:
            # コマンドを同期
            await tree.sync(guild=guild)
            print(f"{guild.name} にコマンドを同期しました")
            
            # 同期後にコマンド一覧を確認
            commands_list = await tree.fetch_commands(guild=guild)
            print(f"{guild.name} のコマンド一覧:")
            if not commands_list:
                print("  登録されているコマンドはありません")
            for command in commands_list:
                print(f" - {command.name}")
        except Exception as e:
            print(f"{guild.name} への同期に失敗: {e}")
    print(f"ログイン成功: {client.user}")

# メッセージ処理
@client.event
async def on_message(message):
    # on_messageが呼ばれているか確認。ねこはどこのチャンネルにもでます
    if message.content == '!neko':
        await message.channel.send('にゃーん')
    try:
        await funcs.handle_message(message, config.allowed_channels_per_guild, chats_per_ch)
    except Exception as e:
        print(f"handle_message でエラー: {e}")

client.run(DISCORD_TOKEN)