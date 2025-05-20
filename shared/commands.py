import discord
import config
import os
import zipfile
import io

MAX_DISCORD_FILESIZE = 8 * 1024 * 1024  # 8MB 制限

def split_files_for_zip(folder_path, max_size=MAX_DISCORD_FILESIZE):
    parts = []
    current_part = []
    current_size = 0

    for root, _, files in os.walk(folder_path):
        for file in files:
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, folder_path)
            file_size = os.path.getsize(full_path)

            # 新しい part を作成
            if current_size + file_size > max_size and current_part:
                parts.append(current_part)
                current_part = []
                current_size = 0

            current_part.append((full_path, relative_path))
            current_size += file_size

    if current_part:
        parts.append(current_part)

    return parts

def reloadconfig():
    config.load_allowed_channels()

def setup(tree, guild=None):
    register_test_command(tree)
    register_add_channel(tree)
    register_remove_channel(tree)
    register_list_channel(tree)
    register_send_chat_zip(tree)

def register_test_command(tree):
    @tree.command(name="test_command", description="テストコマンド")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def test_command(interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_message("!コマンドが登録されています。", ephemeral=True)

def register_add_channel(tree):
    @tree.command(name="add_channel", description="Botが応答するチャンネルを追加します")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def add_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = str(interaction.guild_id)
        channel_id = channel.id
        if guild_id not in config.allowed_channels_per_guild:
            config.allowed_channels_per_guild[guild_id] = []
        if channel_id not in config.allowed_channels_per_guild[guild_id]:
            config.allowed_channels_per_guild[guild_id].append(channel_id)
            config.save_allowed_channels()
            await interaction.response.send_message(f"!<#{channel_id}> を応答チャンネルに追加しました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"!<#{channel_id}> はすでに登録されています。", ephemeral=True)

def register_remove_channel(tree):
    @tree.command(name="remove_channel", description="Botの応答対象からチャンネルを削除します")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def remove_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = str(interaction.guild_id)
        channel_id = channel.id
        if guild_id in config.allowed_channels_per_guild and channel_id in config.allowed_channels_per_guild[guild_id]:
            config.allowed_channels_per_guild[guild_id].remove(channel_id)
            config.save_allowed_channels()
            await interaction.response.send_message(f"!<#{channel_id}> を応答チャンネルから削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"!<#{channel_id}> は登録されていません。", ephemeral=True)

def register_list_channel(tree):
    @tree.command(name="list_channel_slash", description="Botが応答するチャンネルの一覧を表示します")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def list_channel_slash(interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in config.allowed_channels_per_guild or not config.allowed_channels_per_guild[guild_id]:
            await interaction.response.send_message("!このサーバーには応答チャンネルが設定されていません。", ephemeral=True)
            return
        mentions = []
        for ch_id in config.allowed_channels_per_guild[guild_id]:
            ch = interaction.guild.get_channel(ch_id)
            mentions.append(f"<#{ch_id}>" if ch else f"`{ch_id}`（見つかりません）")
        await interaction.response.send_message(
            "!現在設定されている応答チャンネル一覧:\n" + "\n".join(mentions),
            ephemeral=False
        )

def register_send_chat_zip(tree):
    @tree.command(name="send_chat_zip", description="保存されたチャット履歴（ZIP）を送信します")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def send_chat_zip(interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        folder_path = f"/app/shared/saved_chat/{guild_id}"

        if not os.path.exists(folder_path):
            await interaction.response.send_message("!チャット履歴フォルダが存在しません。", ephemeral=True)
            return

        try:
            parts = split_files_for_zip(folder_path)
            if not parts:
                await interaction.response.send_message("!チャット履歴フォルダにファイルがありません。", ephemeral=True)
                return

            await interaction.response.send_message(f"!{len(parts)} 個のファイルに分割して送信します。", ephemeral=True)

            for i, file_group in enumerate(parts, 1):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for full_path, relative_path in file_group:
                        zipf.write(full_path, arcname=relative_path)
                zip_buffer.seek(0)

                filename = f"chat_backup_{guild_id}_part{i}.zip"
                await interaction.channel.send(
                    content=f"!パート {i} を送信します。",
                    file=discord.File(zip_buffer, filename)
                )

        except Exception as e:
            print(f"[send_chat_zip] エラー: {e}")
            await interaction.followup.send("!ZIPファイルの作成または送信に失敗しました。", ephemeral=True)
