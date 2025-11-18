import json
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


class Counting(commands.Cog):
    counting_group = app_commands.Group(name="counting", description="Counting commands")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file = "counting.json"
        self.data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @counting_group.command(name="set", description="Setta il canale di counting e il valore iniziale")
    @app_commands.describe(channel="Canale di testo dove abilitare il counting", start="Valore di partenza (default 0)")
    async def set_count_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, start: int = 0):
        if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message("❌ Devi essere un amministratore o avere Manage Guild.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        next_num = start + 1
        self.data[guild_id] = {
            "channel_id": str(channel.id),
            "last": int(next_num)
        }
        self._save()
        await interaction.response.send_message(f"✅ Counting impostato su {channel.mention}. Messaggio iniziale: `{next_num}`", ephemeral=True)
        try:
            await channel.send(str(next_num))
        except Exception as e:
            print(f"Errore inviando il messaggio nel canale di counting: {e}")

    @counting_group.command(name="unset", description="Disattiva il counting per questo server")
    async def unset_count_channel(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message("❌ Devi essere un amministratore o avere Manage Guild.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        if guild_id in self.data:
            del self.data[guild_id]
            self._save()
            await interaction.response.send_message("✅ Counting disattivato per questo server.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nessun canale di counting impostato per questo server.", ephemeral=True)

    @counting_group.command(name="info", description="Mostra info counting per questo server")
    async def info_counting(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            await interaction.response.send_message("❌ Counting non attivo su questo server.", ephemeral=True)
            return
        channel_id = conf.get("channel_id")
        last = conf.get("last", 0)
        await interaction.response.send_message(f"Counting attivo su <#{channel_id}>. Ultimo numero: `{last}`", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        guild_id = str(message.guild.id)
        conf = self.data.get(guild_id)
        if not conf:
            return
        channel_id = conf.get("channel_id")
        if channel_id != str(message.channel.id):
            return
        content = message.content.strip()
        try:
            num = int(content)
        except ValueError:
            try:
                await message.delete()
            except Exception:
                pass
            return
        expected = int(conf.get("last", 0)) + 1
        if num == expected:
            conf["last"] = int(num)
            self._save()
            try:
                await message.add_reaction("\u2705")
            except Exception:
                pass
        else:
            try:
                await message.delete()
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))
