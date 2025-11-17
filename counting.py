import discord
from discord.ext import commands
import json
import os
from datetime import datetime

class Counting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file = "counting.json"
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, "r", encoding="utf-8") as f:
                try:
                    self.data = json.load(f)
                except Exception:
                    self.data = {"channel_id": None, "count": 0}
        else:
            self.data = {"channel_id": None, "count": 0}

        # Assicura che gli ID siano stringhe (compatibilità strumenti esterni)
        if "channel_id" in self.data and self.data["channel_id"] is not None:
            self.data["channel_id"] = str(self.data["channel_id"])
        if "count" not in self.data:
            self.data["count"] = 0

    def _save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    @commands.hybrid_command(name="setcountchannel", with_app_command=True)
    @commands.has_permissions(administrator=True)
    async def set_count_channel(self, ctx, channel: discord.TextChannel):
        """Imposta il canale dove funziona il counting (admin only)."""
        self.data["channel_id"] = str(channel.id)
        self.data["count"] = 0
        self._save()
        await ctx.reply(f"✅ Canale counting impostato su {channel.mention}. Contatore azzerato.")

    @commands.hybrid_command(name="getcount", with_app_command=True)
    async def get_count(self, ctx):
        """Mostra l'ultimo numero salvato."""
        count = self.data.get("count", 0)
        await ctx.reply(f"📊 Ultimo numero salvato: {count}")

    @commands.hybrid_command(name="resetcount", with_app_command=True)
    @commands.has_permissions(administrator=True)
    async def reset_count(self, ctx, value: int = 0):
        """Resetta il contatore (admin only)."""
        self.data["count"] = value
        self._save()
        await ctx.reply(f"🔄 Contatore resettato a {value}.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora bot e messaggi DMs
        if message.author.bot or not message.guild:
            return

        channel_id = self.data.get("channel_id")
        if not channel_id:
            return

        # Confronto come int (channel_id è una stringa salvata)
        if message.channel.id != int(channel_id):
            return

        content = message.content.strip()
        try:
            number = int(content)
        except ValueError:
            # Non è un numero: rimuovi il messaggio
            try:
                await message.delete()
            except Exception:
                pass
            return

        expected = self.data.get("count", 0) + 1
        if number == expected:
            self.data["count"] = number
            self._save()
            # opzionale: reagisci per conferma
            try:
                await message.add_reaction("✅")
            except Exception:
                pass
        else:
            # numero sbagliato: elimina il messaggio e (opzionale) invia DM
            try:
                await message.delete()
            except Exception:
                pass

async def setup(bot):
    await bot.add_cog(Counting(bot))
