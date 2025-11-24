import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
import time
from typing import Optional, Tuple
from io import BytesIO

from bot_utils import owner_or_has_permissions
import asyncio

# Local async JSON helpers (fallback when json_store is unavailable)
async def load_json(path: str, default):
    try:
        return await asyncio.to_thread(_read_json_file, path, default)
    except Exception:
        return default

def _read_json_file(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

async def save_json(path: str, data):
    try:
        await asyncio.to_thread(_write_json_file, path, data)
    except Exception:
        pass

def _write_json_file(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'levels.json')
DATA_PATH = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')), 'data', 'levels.json')


def load_config():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            "enabled": True,
            "text_xp": {"min": 5, "max": 15, "cooldown_seconds": 60, "excluded_channel_ids": [], "excluded_role_ids": [], "multiplier_roles": {}},
            "voice_xp": {"enabled": True, "per_min_min": 2, "per_min_max": 5, "exclude_muted": True, "exclude_deaf": True, "exclude_afk_channel_ids": [], "excluded_role_ids": [], "multiplier_roles": {}},
            "announce_channel_id": "1381590680518000670",
            "leaderboard": {"page_size": 10},
            "rank_card": {"width": 934, "height": 282, "background": "assets/rankcard/rank_black.png", "bar_color": "#14ff72", "bar_bg": "#1f1f1f", "text_color": "#ffffff", "font_path": "assets/rankcard/Roboto-Bold.ttf"}
        }


def user_has_excluded_role(member: discord.Member, role_ids):
    return any(str(r.id) in set(map(str, role_ids)) for r in member.roles)


def get_multiplier(member: discord.Member, mapping: dict) -> float:
    mult = 1.0
    for rid, factor in mapping.items():
        try:
            if any(str(r.id) == str(rid) for r in member.roles):
                mult = max(mult, float(factor))
        except Exception:
            continue
    return mult


def level_from_xp(total_xp: int) -> Tuple[int, int, int]:
    # Simple curve: next = 5*lvl^2 + 50*lvl + 100
    level = 0
    xp = total_xp
    while True:
        needed = 5 * level * level + 50 * level + 100
        if xp < needed:
            return level, xp, needed
        xp -= needed
        level += 1


class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_config()

    def save_config(self):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    async def _announce_level_up(self, guild: discord.Guild, member: discord.Member, level: int):
        """Annuncia il level-up mostrando una rank card con XP totali e XP mancanti."""
        channel_id = self.config.get('announce_channel_id')
        if not channel_id:
            return
        try:
            ch = guild.get_channel(int(channel_id)) or await guild.fetch_channel(int(channel_id))
        except Exception:
            return
        if not ch:
            return
        # Costruisci embed rank (riusa campi configurati)
        try:
            embed = await self.generate_rank_embed(member)
            embed.title = "🎉 Level Up!"
            embed.description = f"{member.mention} ha raggiunto il livello {level}!"
            data = await load_json(DATA_PATH, {})
            u = data.get(str(guild.id), {}).get('users', {}).get(str(member.id), {"xp": 0})
            total = int(u.get('xp', 0))
            lvl, cur_xp, needed = level_from_xp(total)
            remaining = max(0, needed - cur_xp)
            embed.add_field(name="XP Totale", value=str(total), inline=True)
            embed.add_field(name="XP nel livello", value=f"{cur_xp}/{needed}", inline=True)
            embed.add_field(name="XP al prossimo", value=str(remaining), inline=True)
            file = await self.generate_rank_card_file(member)
            if file:
                embed.set_image(url='attachment://rankcard.png')
                await ch.send(embed=embed, file=file)
            else:
                await ch.send(embed=embed)
        except Exception:
            # Fallback testo semplice
            try:
                await ch.send(f"🎉 {member.mention} ha raggiunto il livello {level}!")
            except Exception:
                pass

    def cog_unload(self):
        try:
            self.voice_loop.cancel()
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        # Migrazione schema: combina text_xp + voice_xp in un unico campo xp se non presente
        try:
            data = await load_json(DATA_PATH, {})
            changed = False
            for gid, g in list(data.items()):
                users = g.get('users', {})
                for uid, u in list(users.items()):
                    if 'xp' not in u:
                        total = int(u.get('text_xp', 0)) + int(u.get('voice_xp', 0)) + int(u.get('xp', 0))
                        users[uid] = {
                            'xp': total,
                            'last_msg_xp_at': int(u.get('last_msg_xp_at', 0))
                        }
                        changed = True
                g['users'] = users
                data[gid] = g
            if changed:
                await save_json(DATA_PATH, data)
        except Exception:
            pass
        self.voice_loop.start()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not self.config.get('enabled', True):
            return
        text_cfg = self.config.get('text_xp', {})
        if str(message.channel.id) in set(map(str, text_cfg.get('excluded_channel_ids', []))):
            return
        if isinstance(message.author, discord.Member) and user_has_excluded_role(message.author, text_cfg.get('excluded_role_ids', [])):
            return

        now = int(time.time())
        cooldown = int(text_cfg.get('cooldown_seconds', 60))
        data = await load_json(DATA_PATH, {})
        gid = str(message.guild.id)
        uid = str(message.author.id)
        g = data.get(gid, {})
        users = g.get('users', {})
        u = users.get(uid, {"xp": 0, "last_msg_xp_at": 0})
        last = int(u.get('last_msg_xp_at', 0) or 0)
        if last and now - last < cooldown:
            return

        amount = random.randint(int(text_cfg.get('min', 5)), int(text_cfg.get('max', 15)))
        mult = get_multiplier(message.author, text_cfg.get('multiplier_roles', {}))
        amount = int(amount * mult)

        prev_total = int(u.get('xp', 0))
        prev_level, _, _ = level_from_xp(prev_total)

        u['xp'] = prev_total + amount
        u['last_msg_xp_at'] = now
        users[uid] = u
        g['users'] = users
        data[gid] = g
        await save_json(DATA_PATH, data)
        new_level, _, _ = level_from_xp(u['xp'])
        if new_level > prev_level and isinstance(message.author, discord.Member):
            await self._announce_level_up(message.guild, message.author, new_level)

    @tasks.loop(minutes=1)
    async def voice_loop(self):
        await self.bot.wait_until_ready()
        # Simple per-minute scan across voice channels for connected members
        try:
            if not self.config.get('voice_xp', {}).get('enabled', True):
                return
            vcfg = self.config.get('voice_xp', {})
            per_min = random.randint(int(vcfg.get('per_min_min', 2)), int(vcfg.get('per_min_max', 5)))
            for guild in self.bot.guilds:
                for vc in guild.voice_channels:
                    if str(vc.id) in set(map(str, vcfg.get('exclude_afk_channel_ids', []))):
                        continue
                    members = [m for m in vc.members if not m.bot]
                    for m in members:
                        if isinstance(m, discord.Member):
                            if vcfg.get('exclude_muted', True) and (m.voice.self_mute or m.voice.mute):
                                continue
                            if vcfg.get('exclude_deaf', True) and (m.voice.self_deaf or m.voice.deaf):
                                continue
                            if user_has_excluded_role(m, vcfg.get('excluded_role_ids', [])):
                                continue
                            mult = get_multiplier(m, vcfg.get('multiplier_roles', {}))
                            amount = int(per_min * mult)
                            data = await load_json(DATA_PATH, {})
                            gid = str(guild.id)
                            uid = str(m.id)
                            g = data.get(gid, {})
                            users = g.get('users', {})
                            u = users.get(uid, {"xp": 0, "last_msg_xp_at": 0})
                            prev_total = int(u.get('xp', 0))
                            prev_level_prev, _, _ = level_from_xp(prev_total)
                            u['xp'] = prev_total + amount
                            users[uid] = u
                            g['users'] = users
                            data[gid] = g
                            await save_json(DATA_PATH, data)
                            new_level_after, _, _ = level_from_xp(u['xp'])
                            if new_level_after > prev_level_prev:
                                await self._announce_level_up(guild, m, new_level_after)
        except Exception:
            pass

    @voice_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()

    async def generate_rank_embed(self, member: discord.Member) -> discord.Embed:
        cfg = self.config.get('rank_embed', {})
        # Fetch XP from JSON
        data = await load_json(DATA_PATH, {})
        gid = str(member.guild.id)
        uid = str(member.id)
        users = data.get(gid, {}).get('users', {})
        u = users.get(uid, {"xp": 0})
        xp = int(u.get('xp', 0))
        level, cur_xp, needed = level_from_xp(xp)
        progress = int((cur_xp / needed) * 100) if needed > 0 else 100

        embed = discord.Embed(
            title=cfg.get('title', 'Rank Card'),
            description=cfg.get('description', '{user} - Livello {level}').format(
                user=member.display_name,
                level=level
            ),
            color=int(cfg.get('color', '#14ff72').lstrip('#'), 16)
        )

        thumbnail = cfg.get('thumbnail', '{avatar}')
        if '{avatar}' in thumbnail:
            embed.set_thumbnail(url=member.display_avatar.url)
        elif thumbnail:
            embed.set_thumbnail(url=thumbnail)

        for field in cfg.get('fields', []):
            name = field.get('name', '').format(xp=xp, remaining=needed - cur_xp, progress=progress)
            value = field.get('value', '').format(xp=xp, remaining=needed - cur_xp, progress=progress)
            inline = field.get('inline', True)
            embed.add_field(name=name, value=value, inline=inline)

        footer = cfg.get('footer', '')
        if footer:
            embed.set_footer(text=footer)

        return embed

    async def generate_rank_card_file(self, member: discord.Member) -> Optional[discord.File]:
        """Genera un'immagine della rank card da allegare (se Pillow disponibile)."""
        card_cfg = self.config.get('rank_card', {})
        bg_path = card_cfg.get('background')
        if not bg_path:
            return None
        # Determina XP
        data = await load_json(DATA_PATH, {})
        u = data.get(str(member.guild.id), {}).get('users', {}).get(str(member.id), {"xp": 0})
        total = int(u.get('xp', 0))
        level, cur_xp, needed = level_from_xp(total)
        remaining = max(0, needed - cur_xp)
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return None
        try:
            width = int(card_cfg.get('width', 934))
            height = int(card_cfg.get('height', 282))
            bar_color = card_cfg.get('bar_color', '#14ff72')
            bar_bg = card_cfg.get('bar_bg', '#1f1f1f')
            text_color = card_cfg.get('text_color', '#ffffff')
            font_path = card_cfg.get('font_path')
            # Carica sfondo
            if os.path.isfile(bg_path):
                base = Image.open(bg_path).convert('RGBA').resize((width, height))
            else:
                base = Image.new('RGBA', (width, height), (30, 30, 30, 255))
            draw = ImageDraw.Draw(base)
            # Font fallback
            try:
                font_large = ImageFont.truetype(font_path, 46) if font_path and os.path.isfile(font_path) else ImageFont.load_default()
                font_small = ImageFont.truetype(font_path, 28) if font_path and os.path.isfile(font_path) else ImageFont.load_default()
            except Exception:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            # Testo utente e livello
            name_text = f"{member.display_name}"[:25]
            level_text = f"Level {level}"  
            draw.text((30, 30), name_text, fill=text_color, font=font_large)
            draw.text((30, 90), level_text, fill=text_color, font=font_small)
            # Progress bar
            bar_x, bar_y = 30, height - 90
            bar_w, bar_h = width - 60, 40
            # sfondo barra
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=20, fill=bar_bg)
            pct = 0 if needed == 0 else cur_xp / needed
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=20, fill=bar_color)
            prog_text = f"{cur_xp}/{needed} XP • Mancano {remaining}"  
            tw, th = draw.textsize(prog_text, font=font_small)
            draw.text((bar_x + (bar_w - tw)//2, bar_y + (bar_h - th)//2), prog_text, fill=text_color, font=font_small)
            # Avatar cerchio
            try:
                avatar_asset = member.display_avatar.url
                # Scarica avatar
                import requests
                resp = requests.get(avatar_asset, timeout=5)
                if resp.status_code == 200:
                    avatar_img = Image.open(BytesIO(resp.content)).convert('RGBA').resize((180, 180))
                    mask = Image.new('L', (180, 180), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0,0,180,180), fill=255)
                    base.paste(avatar_img, (width - 210, 30), mask)
            except Exception:
                pass
            bio = BytesIO()
            base.save(bio, format='PNG')
            bio.seek(0)
            return discord.File(bio, filename='rankcard.png')
        except Exception:
            return None
    
    level = app_commands.Group(name='level', description='Comandi relativi ai livelli e XP')

    @level.command(name='rank', description='Mostra la tua rank card (totale)')
    @app_commands.describe(user='Utente da mostrare')
    async def slash_rank(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        member = user or interaction.user
        embed = await self.generate_rank_embed(member)
        file = await self.generate_rank_card_file(member)
        if file:
            embed.set_image(url='attachment://rankcard.png')
            await interaction.response.send_message(embed=embed, file=file, ephemeral=False)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=False)

    @level.command(name='leaderboard', description='Mostra la classifica XP totale')
    @app_commands.describe(page='Pagina (da 1)')
    async def slash_leaderboard(self, interaction: discord.Interaction, page: Optional[int] = 1):
        await interaction.response.defer()
        page = max(1, int(page or 1))
        page_size = int(self.config.get('leaderboard', {}).get('page_size', 10))
        offset = (page - 1) * page_size
        data = await load_json(DATA_PATH, {})
        gid = str(interaction.guild.id)
        users = data.get(gid, {}).get('users', {})
        items = []
        for uid, u in users.items():
            total = int(u.get('xp', 0))
            items.append((int(uid), total))
        items.sort(key=lambda x: x[1], reverse=True)
        slice_items = items[offset:offset + page_size]
        if not slice_items:
            await interaction.followup.send('Nessun dato in classifica.')
            return
        desc = []
        rank_start = offset + 1
        for i, (uid, xp) in enumerate(slice_items, start=rank_start):
            user = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            desc.append(f"**#{i}** {user.mention if user else uid} — {xp} XP")
        embed = discord.Embed(title="Classifica Globale", description='\n'.join(desc), color=0x14ff72)
        await interaction.followup.send(embed=embed)

    @level.command(name='setchannel', description='Imposta il canale per gli annunci di level-up (admin o manage_guild)')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(channel='Canale dove annunciare i level-up')
    async def slash_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.config['announce_channel_id'] = str(channel.id)
        self.save_config()
        await interaction.response.send_message(f'✅ Canale di annunci impostato su {channel.mention}.', ephemeral=True)

    @level.command(name='stats', description='Mostra le statistiche di livello totale')
    @app_commands.describe(user='Utente da mostrare')
    async def slash_stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        member = user or interaction.user
        data = await load_json(DATA_PATH, {})
        gid = str(interaction.guild.id)
        uid = str(member.id)
        users = data.get(gid, {}).get('users', {})
        u = users.get(uid, {"xp": 0})
        total_xp = int(u.get('xp', 0))
        level, cur_xp, needed = level_from_xp(total_xp)
        remaining = max(0, needed - cur_xp)
        embed = discord.Embed(title="Statistiche Totali", color=0x14ff72)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name='Livello', value=str(level))
        embed.add_field(name='XP totale', value=str(total_xp))
        embed.add_field(name='XP nel livello', value=f"{cur_xp}/{needed}")
        embed.add_field(name='XP mancanti al prossimo', value=str(remaining), inline=False)
        await interaction.response.send_message(embed=embed)

    @level.command(name='givexp', description='Aggiunge XP totali a un utente (solo admin)')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(user='Utente', amount='Quantità da aggiungere')
    async def slash_givexp(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        data = await load_json(DATA_PATH, {})
        gid = str(interaction.guild.id)
        uid = str(user.id)
        g = data.get(gid, {})
        users = g.get('users', {})
        u = users.get(uid, {"xp": 0, "last_msg_xp_at": 0})
        u['xp'] = int(u.get('xp', 0)) + int(amount)
        users[uid] = u
        g['users'] = users
        data[gid] = g
        await save_json(DATA_PATH, data)
        await interaction.response.send_message(f'Aggiunti {amount} XP totali a {user.mention}.', ephemeral=True)

    @level.command(name='setxp', description='Imposta gli XP totali di un utente (solo admin)')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(user='Utente', amount='Nuovo totale XP')
    async def slash_setxp(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        data = await load_json(DATA_PATH, {})
        gid = str(interaction.guild.id)
        uid = str(user.id)
        g = data.get(gid, {})
        users = g.get('users', {})
        u = users.get(uid, {"xp": 0, "last_msg_xp_at": 0})
        u['xp'] = int(amount)
        users[uid] = u
        g['users'] = users
        data[gid] = g
        await save_json(DATA_PATH, data)
        await interaction.response.send_message(f'Settati {amount} XP totali per {user.mention}.', ephemeral=True)


async def setup(bot: commands.Bot):
    cog = LevelsCog(bot)
    await bot.add_cog(cog)
    try:
        if bot.tree.get_command('level') is None:
            bot.tree.add_command(cog.level)
    except Exception as e:
        print(f'Errore registrando gruppo level: {e}')
# python -m pip install -U discord.py requests python-dotenv PyNaCl
