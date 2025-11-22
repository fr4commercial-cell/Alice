import time
from typing import Optional, Dict, Any, Tuple, List
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from .coralmc_client import CoralMCClient, PlayerStats, PlayerInfo
try:
    from .console_logger import logger
except Exception:
    import logging
    logger = logging.getLogger('coralmc')




class CoralMCCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = CoralMCClient()
        self.cache_ttl: int = 300  # seconds
        self.cache_stats: Dict[str, Tuple[float, PlayerStats]] = {}
        self.cache_info: Dict[str, Tuple[float, PlayerInfo]] = {}
        self._rate_limit: Dict[int, float] = {}  # user_id -> last used timestamp
        self.rate_window = 3  # seconds between uses
        # Rimosso supporto WinStreak leaderboard

    async def _safe_defer(self, interaction: discord.Interaction, ephemeral: bool):
        """Tenta il defer senza sollevare 404 Unknown interaction se già risposto."""
        if interaction.response.is_done():
            return
        try:
            await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        except (discord.NotFound, discord.HTTPException):
            # Ignora token scaduto o già usato
            pass

    async def cog_unload(self):
        try:
            await self.client.close()
        except Exception:
            pass

    coralmc_group = app_commands.Group(name='coralmc', description='Info CoralMC')

    def _check_rate(self, interaction: discord.Interaction) -> bool:
        now = time.time()
        last = self._rate_limit.get(interaction.user.id, 0)
        if now - last < self.rate_window:
            return False
        self._rate_limit[interaction.user.id] = now
        return True

    def _build_stats_embed(self, username: str, stats: PlayerStats, source: str) -> discord.Embed:
        bed = stats.bedwars
        # Calcoli utili
        wins = bed.get('wins', 0)
        losses = bed.get('losses', 0)
        kills = bed.get('kills', 0)
        deaths = bed.get('deaths', 0)
        fk = bed.get('final_kills', 0)
        fd = bed.get('final_deaths', 0)
        coins = bed.get('coins', 0)
        level = bed.get('level', 0)
        ws = bed.get('winstreak', 0)
        best_ws = bed.get('highest_winstreak', 0)
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
        kd = (kills / deaths) if deaths > 0 else kills
        fkdr = (fk / fd) if fd > 0 else fk
        # Colore dinamico (verde se winrate alto, rosso se basso)
        if win_rate >= 70:
            color = 0x2ECC71
        elif win_rate >= 50:
            color = 0xF1C40F
        else:
            color = 0xE74C3C
        embed = discord.Embed(title=f"🛏️ BedWars Stats • {username}", color=color)
        win_bar = self._make_bar(win_rate / 100.0, 20)
        ws_ratio = min(ws / best_ws, 1.0) if best_ws > 0 else 0
        ws_bar = self._make_bar(ws_ratio, 20)
        embed.description = (
            f"**Livello:** `{level}` | **Coins:** `{coins}`\n"
            f"**Win Rate:** `{win_rate:.1f}%` {win_bar}\n"
            f"**Winstreak:** `{ws}` (Best `{best_ws}`) {ws_bar}"
        )
        embed.add_field(name='Prestazioni', value=(
            f"Wins / Losses: `{wins}` / `{losses}`\n"
            f"Kills / Deaths: `{kills}` / `{deaths}` → K/D `{kd:.2f}`\n"
            f"Final K / D: `{fk}` / `{fd}` → FK/D `{fkdr:.2f}`"
        ), inline=False)
        embed.add_field(name='Progressione', value=(
            f"Esperienza: `{bed.get('experience', 0)}`"
        ), inline=True)
        # Avatar Minecraft (placeholder se non disponibile)
        avatar_url = f"https://mc-heads.net/avatar/{username}/128"
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f'Fonte: {source} • TTL {self.cache_ttl}s')
        return embed

    def _make_bar(self, ratio: float, length: int = 10) -> str:
        ratio = max(0.0, min(1.0, ratio))
        filled = int(round(ratio * length))
        empty = length - filled
        return '`' + '█' * filled + '·' * empty + '`'

    @coralmc_group.command(name='stats', description='Mostra le statistiche Bedwars / KitPvP di un giocatore')
    @app_commands.describe(username='Username Minecraft', public='Se true risposta visibile a tutti')
    async def stats_cmd(self, interaction: discord.Interaction, username: str, public: bool = False):
        if not self._check_rate(interaction):
            await interaction.response.send_message('⏳ Riprova tra qualche secondo.', ephemeral=True)
            return
        await self._safe_defer(interaction, ephemeral=not public)
        if not self.client.is_username_valid(username):
            await interaction.followup.send('❌ Username non valido.', ephemeral=not public)
            return
        uname = username.strip()
        try:
            now = time.time()
            cached = self.cache_stats.get(uname.lower())
            stats: Optional[PlayerStats] = None
            if cached and now - cached[0] < self.cache_ttl:
                stats = cached[1]
            else:
                stats = await self.client.get_player_stats(uname)
                if stats:
                    self.cache_stats[uname.lower()] = (now, stats)
            if not stats:
                await interaction.followup.send('❌ Giocatore non trovato o errore API.', ephemeral=not public)
                return
            source = 'CACHE' if cached and now - cached[0] < self.cache_ttl else 'LIVE'
            embed = self._build_stats_embed(uname, stats, source)
            await interaction.followup.send(embed=embed, ephemeral=not public)
        except Exception as e:
            logger.error(f'Errore stats coralmc: {e}')
            await interaction.followup.send('❌ Errore recuperando dati.', ephemeral=not public)

    @coralmc_group.command(name='info', description='Mostra info rank e ban di un giocatore')
    @app_commands.describe(username='Username Minecraft', public='Se true risposta visibile a tutti')
    async def info_cmd(self, interaction: discord.Interaction, username: str, public: bool = False):
        if not self._check_rate(interaction):
            await interaction.response.send_message('⏳ Riprova tra qualche secondo.', ephemeral=True)
            return
        await self._safe_defer(interaction, ephemeral=not public)
        if not self.client.is_username_valid(username):
            await interaction.followup.send('❌ Username non valido.', ephemeral=not public)
            return
        uname = username.strip()
        try:
            now = time.time()
            cached = self.cache_info.get(uname.lower())
            info: Optional[PlayerInfo] = None
            if cached and now - cached[0] < self.cache_ttl:
                info = cached[1]
            else:
                info = await self.client.get_player_info(uname)
                if info:
                    self.cache_info[uname.lower()] = (now, info)
            if not info:
                await interaction.followup.send('❌ Giocatore non trovato o errore API.', ephemeral=not public)
                return
            ranks = info.ranks
            rank_bw = ranks.get('bedwars') or 'Nessuno'
            raw_bw = ranks['raw'].get('bedwars') or 'N/A'
            # Colore basato sul rank
            rank_color_map = {
                'Nessuno': 0x7F8C8D,
                'Bronze': 0xCD7F32,
                'Silver': 0xBDC3C7,
                'Gold': 0xF1C40F,
                'Emerald': 0x2ECC71,
                'Diamond': 0x3498DB,
                'Master': 0x9B59B6,
                'Legend': 0xE67E22,
                'Mythic': 0x8E44AD,
            }
            rank_emoji_map = {
                'Nessuno': '➖',
                'Bronze': '🥉',
                'Silver': '🥈',
                'Gold': '🥇',
                'Emerald': '💚',
                'Diamond': '💎',
                'Master': '🧠',
                'Legend': '🔥',
                'Mythic': '🛡️',
            }
            color = rank_color_map.get(rank_bw, 0x3498DB)
            embed = discord.Embed(title=f"🛏️ BedWars Rank • {info.username}", color=color)
            stato = '🚫 Bannato' if info.is_banned else '✅ Attivo'
            emoji = rank_emoji_map.get(rank_bw, '➖')
            embed.description = f"**Stato:** {stato}\n**Rank:** {emoji} `{rank_bw}`\n**Raw:** `{raw_bw}`"
            avatar_url = f"https://mc-heads.net/avatar/{info.username}/128"
            embed.set_thumbnail(url=avatar_url)
            source = 'CACHE' if cached and now - cached[0] < self.cache_ttl else 'LIVE'
            embed.set_footer(text=f'Fonte: {source} • TTL {self.cache_ttl}s')
            await interaction.followup.send(embed=embed, ephemeral=not public)
        except Exception as e:
            logger.error(f'Errore info coralmc: {e}')
            await interaction.followup.send('❌ Errore recuperando dati.', ephemeral=not public)

    @coralmc_group.command(name='clearcache', description='Svuota la cache CoralMC')
    async def clearcache_cmd(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('❌ Permessi insufficienti.', ephemeral=True)
            return
        self.cache_stats.clear()
        self.cache_info.clear()
        await interaction.response.send_message('✅ Cache svuotata.', ephemeral=True)

    @coralmc_group.command(name='purge', description='Rimuove dalla cache un singolo username')
    @app_commands.describe(username='Username Minecraft')
    async def purge_cmd(self, interaction: discord.Interaction, username: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('❌ Permessi insufficienti.', ephemeral=True)
            return
        uname = username.lower()
        removed = False
        if uname in self.cache_info:
            del self.cache_info[uname]
            removed = True
        if uname in self.cache_stats:
            del self.cache_stats[uname]
            removed = True
        await interaction.response.send_message('✅ Cache entry rimossa.' if removed else 'ℹ️ Nessuna voce cache trovata.', ephemeral=True)

    @coralmc_group.command(name='setttl', description='Imposta TTL cache CoralMC (secondi)')
    @app_commands.describe(seconds='Secondi (min 30, max 3600)')
    async def setttl_cmd(self, interaction: discord.Interaction, seconds: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('❌ Permessi insufficienti.', ephemeral=True)
            return
        if seconds < 30 or seconds > 3600:
            await interaction.response.send_message('❌ Valore fuori range (30-3600).', ephemeral=True)
            return
        self.cache_ttl = seconds
        await interaction.response.send_message(f'✅ TTL impostato a {seconds}s.', ephemeral=True)

    @coralmc_group.command(name='ping', description='Mostra la latenza dell\'API CoralMC')
    async def ping_cmd(self, interaction: discord.Interaction):
        start = time.perf_counter()
        data = await self.client._get_json(f'{self.client.BASE_URL}dummy_invalid_user')
        elapsed = (time.perf_counter() - start) * 1000
        status = data.get('error', 'ok')
        await interaction.response.send_message(f'🌐 CoralMC API ping: {elapsed:.0f}ms (status: {status})', ephemeral=True)

    @coralmc_group.command(name='combined', description='Mostra info + stats insieme')
    @app_commands.describe(username='Username Minecraft', public='Se true risposta visibile a tutti')
    async def combined_cmd(self, interaction: discord.Interaction, username: str, public: bool = False):
        if not self._check_rate(interaction):
            await interaction.response.send_message('⏳ Riprova tra qualche secondo.', ephemeral=True)
            return
        await self._safe_defer(interaction, ephemeral=not public)
        if not self.client.is_username_valid(username):
            await interaction.followup.send('❌ Username non valido.', ephemeral=not public)
            return
        uname = username.strip()
        try:
            now = time.time()
            # Info cache
            cached_info = self.cache_info.get(uname.lower())
            info: Optional[PlayerInfo] = None
            if cached_info and now - cached_info[0] < self.cache_ttl:
                info = cached_info[1]
            else:
                info = await self.client.get_player_info(uname)
                if info:
                    self.cache_info[uname.lower()] = (now, info)
            # Stats cache
            cached_stats = self.cache_stats.get(uname.lower())
            stats: Optional[PlayerStats] = None
            if cached_stats and now - cached_stats[0] < self.cache_ttl:
                stats = cached_stats[1]
            else:
                stats = await self.client.get_player_stats(uname)
                if stats:
                    self.cache_stats[uname.lower()] = (now, stats)
            if not info and not stats:
                await interaction.followup.send('❌ Giocatore non trovato o errore API.', ephemeral=not public)
                return
            bed = stats.bedwars if stats else {}
            wins = bed.get('wins', 0)
            losses = bed.get('losses', 0)
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
            if win_rate >= 70:
                color = 0x2ECC71
            elif win_rate >= 50:
                color = 0xF1C40F
            else:
                color = 0xE74C3C
            embed = discord.Embed(title=f"🛏️ BedWars • {uname}", color=color)
            if info:
                rank_bw = info.ranks.get('bedwars') or 'Nessuno'
                raw_bw = info.ranks['raw'].get('bedwars') or 'N/A'
                embed.add_field(name='Rank', value=f"{rank_bw}\nRaw: `{raw_bw}`", inline=True)
            if stats:
                kills = bed.get('kills', 0)
                deaths = bed.get('deaths', 0)
                fk = bed.get('final_kills', 0)
                fd = bed.get('final_deaths', 0)
                kd = (kills / deaths) if deaths > 0 else kills
                fkdr = (fk / fd) if fd > 0 else fk
                ws = bed.get('winstreak', 0)
                best_ws = bed.get('highest_winstreak', 0)
                level = bed.get('level', 0)
                win_bar = self._make_bar(win_rate / 100.0, 15)
                ws_ratio = min(ws / best_ws, 1.0) if best_ws > 0 else 0
                ws_bar = self._make_bar(ws_ratio, 15)
                embed.add_field(name='Stats', value=(
                    f"Lv `{level}` | WR `{win_rate:.1f}%` {win_bar}\n"
                    f"W/L: `{wins}`/`{losses}` WS `{ws}` (Best `{best_ws}`) {ws_bar}\n"
                    f"K/D: `{kills}`/`{deaths}` → `{kd:.2f}` | FK/D: `{fk}`/`{fd}` → `{fkdr:.2f}`"
                ), inline=False)
            avatar_url = f"https://mc-heads.net/avatar/{uname}/128"
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f'Fonte: combinata • TTL {self.cache_ttl}s')
            await interaction.followup.send(embed=embed, ephemeral=not public)
        except Exception as e:
            logger.error(f'Errore combined coralmc: {e}')
            await interaction.followup.send('❌ Errore recuperando dati.', ephemeral=not public)


async def setup(bot: commands.Bot):
    cog = CoralMCCog(bot)
    await bot.add_cog(cog)
    try:
        if bot.tree.get_command('coralmc') is None:
            bot.tree.add_command(cog.coralmc_group)
    except Exception as e:
        logger.error(f'Errore registrando gruppo coralmc: {e}')
