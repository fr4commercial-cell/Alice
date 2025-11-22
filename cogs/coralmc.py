import aiohttp
import re
import time
from typing import Optional, Dict, Any, Tuple
import discord
from discord import app_commands
from discord.ext import commands
try:
    from .console_logger import logger
except Exception:
    import logging
    logger = logging.getLogger('coralmc')


class PlayerInfo:
    def __init__(self, username: str, is_banned: bool, ranks: Dict[str, Any]):
        self.username: str = username
        self.is_banned: bool = is_banned
        self.ranks: Dict[str, Any] = ranks

    @staticmethod
    def get_formatted_rank(raw_rank: Optional[str]) -> Optional[str]:
        """Format the rank by removing all non-uppercase letters."""
        if raw_rank is None:
            return None
        formatted_rank = re.sub(r"[^A-Z]", "", raw_rank)
        return formatted_rank if formatted_rank else None

    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> Optional['PlayerInfo']:
        """Create a PlayerInfo instance from a JSON response."""
        if not json_data.get("username"):
            return None

        ranks = {
            "global": cls.get_formatted_rank(json_data.get("globalRank")),
            "bedwars": cls.get_formatted_rank(json_data.get("vipBedwars")),
            "kitpvp": cls.get_formatted_rank(json_data.get("vipKitpvp")),
            "raw": {
                "global": json_data.get("globalRank"),
                "bedwars": json_data.get("vipBedwars"),
                "kitpvp": json_data.get("vipKitpvp"),
            }
        }
        return cls(
            username=json_data["username"],
            is_banned=json_data.get("isBanned", False),
            ranks=ranks
        )


class PlayerStats:
    def __init__(self, bedwars: Dict[str, Any], kitpvp: Dict[str, Any]):
        self.bedwars: Dict[str, Any] = bedwars
        self.kitpvp: Dict[str, Any] = kitpvp

    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> 'PlayerStats':
        """Create a PlayerStats instance from a JSON response."""
        bedwars = json_data.get("bedwars", {})
        kitpvp = json_data.get("kitpvp", {})

        return cls(
            bedwars={
                "level": bedwars.get("level", 0),
                "experience": bedwars.get("exp", 0),
                "coins": bedwars.get("coins", 0),
                "kills": bedwars.get("kills", 0),
                "deaths": bedwars.get("deaths", 0),
                "final_kills": bedwars.get("final_kills", 0),
                "final_deaths": bedwars.get("final_deaths", 0),
                "wins": bedwars.get("wins", 0),
                "losses": bedwars.get("played", 0) - bedwars.get("wins", 0),
                "winstreak": bedwars.get("winstreak", 0),
                "highest_winstreak": bedwars.get("h_winstreak", 0),
            },
            kitpvp={
                "balance": kitpvp.get("balance", 0),
                "kills": kitpvp.get("kills", 0),
                "deaths": kitpvp.get("deaths", 0),
                "bounty": kitpvp.get("bounty", 0),
                "highest_bounty": kitpvp.get("topBounty", 0),
                "streak": kitpvp.get("streak", 0),
                "highest_streak": kitpvp.get("topstreak", 0),
            }
        )


class CoralMCClient:
    BASE_URL: str = "https://api.coralmc.it/api/user/"

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    @staticmethod
    def is_username_valid(username: str) -> bool:
        """Check if the username is valid (3-16 chars, alphanumeric, or underscores)."""
        return 3 <= len(username) <= 16 and bool(re.match(r"^[a-zA-Z0-9_]+$", username))

    async def _get_json(self, endpoint: str) -> Dict[str, Any]:
        """Perform a GET request and return the JSON response with basic error handling."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        try:
            async with self.session.get(endpoint) as response:
                if response.status != 200:
                    return {"error": f"status_{response.status}"}
                return await response.json()
        except aiohttp.ClientError as e:
            return {"error": f"client_{e.__class__.__name__}"}

    async def get_player_stats(self, username: str) -> Optional[PlayerStats]:
        """Fetch and return player stats for Bedwars and KitPvP."""
        if not self.is_username_valid(username):
            return None

        if self.session is None:
            self.session = aiohttp.ClientSession()

        json_data = await self._get_json(f"{self.BASE_URL}{username}")

        if json_data.get("error") is not None:
            return None

        return PlayerStats.from_json(json_data)

    async def get_player_info(self, username: str) -> Optional[PlayerInfo]:
        """Fetch and return basic player info, including ranks and ban status."""
        if not self.is_username_valid(username):
            return None

        if self.session is None:
            self.session = aiohttp.ClientSession()

        json_data = await self._get_json(f"{self.BASE_URL}{username}/infos")

        return PlayerInfo.from_json(json_data)

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None


class CoralMCCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = CoralMCClient()
        self.cache_ttl: int = 300  # seconds
        self.cache_stats: Dict[str, Tuple[float, PlayerStats]] = {}
        self.cache_info: Dict[str, Tuple[float, PlayerInfo]] = {}

    async def cog_unload(self):
        try:
            await self.client.close()
        except Exception:
            pass

    coralmc_group = app_commands.Group(name='coralmc', description='Info CoralMC')

    @coralmc_group.command(name='stats', description='Mostra le statistiche Bedwars / KitPvP di un giocatore')
    @app_commands.describe(username='Username Minecraft', public='Se true risposta visibile a tutti')
    async def stats_cmd(self, interaction: discord.Interaction, username: str, public: bool = False):
        await interaction.response.defer(ephemeral=not public, thinking=True)
        if not self.client.is_username_valid(username):
            await interaction.followup.send('❌ Username non valido.', ephemeral=not public)
            return
        try:
            # Cache lookup
            now = time.time()
            cached = self.cache_stats.get(username.lower())
            stats: Optional[PlayerStats] = None
            if cached and now - cached[0] < self.cache_ttl:
                stats = cached[1]
            else:
                stats = await self.client.get_player_stats(username)
                if stats:
                    self.cache_stats[username.lower()] = (now, stats)
            if not stats:
                await interaction.followup.send('❌ Giocatore non trovato o errore API.', ephemeral=not public)
                return
            bed = stats.bedwars
            kit = stats.kitpvp
            embed = discord.Embed(title=f'Statistiche {username}', color=0x1ABC9C)
            embed.add_field(name='Bedwars', value=(
                f"Livello: {bed['level']}\nExp: {bed['experience']}\nCoins: {bed['coins']}\n"
                f"Kills: {bed['kills']} / Deaths: {bed['deaths']}\nFinal K: {bed['final_kills']} / Final D: {bed['final_deaths']}\n"
                f"Wins: {bed['wins']} / Losses: {bed['losses']}\nWinstreak: {bed['winstreak']} (High {bed['highest_winstreak']})"
            ), inline=False)
            embed.add_field(name='KitPvP', value=(
                f"Balance: {kit['balance']}\nKills: {kit['kills']} / Deaths: {kit['deaths']}\n"
                f"Bounty: {kit['bounty']} (High {kit['highest_bounty']})\nStreak: {kit['streak']} (High {kit['highest_streak']})"
            ), inline=False)
            source = 'CACHE' if cached and now - cached[0] < self.cache_ttl else 'LIVE'
            embed.set_footer(text=f"Fonte: {source} | TTL {self.cache_ttl}s")
            await interaction.followup.send(embed=embed, ephemeral=not public)
        except Exception as e:
            logger.error(f'Errore stats coralmc: {e}')
            await interaction.followup.send('❌ Errore recuperando dati.', ephemeral=not public)

    @coralmc_group.command(name='info', description='Mostra info rank e ban di un giocatore')
    @app_commands.describe(username='Username Minecraft', public='Se true risposta visibile a tutti')
    async def info_cmd(self, interaction: discord.Interaction, username: str, public: bool = False):
        await interaction.response.defer(ephemeral=not public, thinking=True)
        if not self.client.is_username_valid(username):
            await interaction.followup.send('❌ Username non valido.', ephemeral=not public)
            return
        try:
            now = time.time()
            cached = self.cache_info.get(username.lower())
            info: Optional[PlayerInfo] = None
            if cached and now - cached[0] < self.cache_ttl:
                info = cached[1]
            else:
                info = await self.client.get_player_info(username)
                if info:
                    self.cache_info[username.lower()] = (now, info)
            if not info:
                await interaction.followup.send('❌ Giocatore non trovato o errore API.', ephemeral=not public)
                return
            embed = discord.Embed(title=f'Info {info.username}', color=0x3498DB)
            embed.add_field(name='Banned', value='✅ Sì' if info.is_banned else '❌ No', inline=True)
            ranks = info.ranks
            embed.add_field(name='Rank Global', value=ranks.get('global') or 'Nessuno', inline=True)
            embed.add_field(name='Rank Bedwars', value=ranks.get('bedwars') or 'Nessuno', inline=True)
            embed.add_field(name='Rank KitPvP', value=ranks.get('kitpvp') or 'Nessuno', inline=True)
            raw_global = ranks['raw'].get('global')
            raw_bw = ranks['raw'].get('bedwars')
            raw_kp = ranks['raw'].get('kitpvp')
            embed.add_field(name='Raw Global', value=raw_global or 'N/A', inline=True)
            embed.add_field(name='Raw Bedwars', value=raw_bw or 'N/A', inline=True)
            embed.add_field(name='Raw KitPvP', value=raw_kp or 'N/A', inline=True)
            source = 'CACHE' if cached and now - cached[0] < self.cache_ttl else 'LIVE'
            embed.set_footer(text=f"Fonte: {source} | TTL {self.cache_ttl}s")
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

async def setup(bot: commands.Bot):
    cog = CoralMCCog(bot)
    await bot.add_cog(cog)
    try:
        if bot.tree.get_command('coralmc') is None:
            bot.tree.add_command(cog.coralmc_group)
    except Exception as e:
        logger.error(f'Errore registrando gruppo coralmc: {e}')