import discord
from discord.ext import commands
from discord import ui, app_commands
import json
import os
from bot_utils import owner_or_has_permissions

# Path config (root)
BASE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config.json')

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg: dict):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

class VerifyView(ui.View):
    def __init__(self, role_id: int | None):
        super().__init__(timeout=None)
        self.role_id = role_id

    @ui.button(label='Verificati', style=discord.ButtonStyle.success, custom_id='verify_button')
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.bot:
            await interaction.response.send_message('I bot non possono essere verificati.', ephemeral=True)
            return
        cfg = load_config().get('verification', {})
        role = None
        if self.role_id:
            role = interaction.guild.get_role(self.role_id)
        if role is None:
            # fallback: search by name if stored name present
            name = cfg.get('role_name', 'Verified')
            role = discord.utils.get(interaction.guild.roles, name=name)
        if role is None:
            name = cfg.get('role_name', 'Verified')
            role = await interaction.guild.create_role(name=name)
        try:
            await interaction.user.add_roles(role, reason='User verified')
        except Exception:
            await interaction.response.send_message('❌ Errore nel dare il ruolo di verifica.', ephemeral=True)
            return
        await interaction.response.send_message('✅ Verifica completata! Ora hai accesso al server.', ephemeral=True)

class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        if 'verification' not in self.config:
            self.config['verification'] = {}
            save_config(self.config)

    def _get_verification_cfg(self):
        self.config = load_config()
        return self.config.setdefault('verification', {})

    def _save_verification_cfg(self, data: dict):
        self.config = load_config()
        self.config['verification'] = data
        save_config(self.config)

    async def _send_panel(self, channel: discord.TextChannel, *, replace: bool = False):
        ver_cfg = self._get_verification_cfg()
        role_id = ver_cfg.get('role_id')
        # Clean previous message if replace
        if replace:
            try:
                old_id = ver_cfg.get('message_id')
                if old_id:
                    msg = await channel.fetch_message(int(old_id))
                    await msg.delete()
            except Exception:
                pass
        view = VerifyView(role_id)
        content = ver_cfg.get('panel_text', 'Clicca il bottone per verificarti!')
        msg = await channel.send(content, view=view)
        ver_cfg['message_id'] = msg.id
        self._save_verification_cfg(ver_cfg)

    @commands.Cog.listener()
    async def on_ready(self):
        # Optionally resend panel if configured with auto_resend
        ver_cfg = self._get_verification_cfg()
        channel_id = ver_cfg.get('channel_id')
        auto = ver_cfg.get('auto_resend', False)
        if channel_id and auto:
            channel = self.bot.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                try:
                    await self._send_panel(channel, replace=False)
                except Exception:
                    pass

    verify_group = app_commands.Group(name='verify', description='Gestione verifica utenti')

    @verify_group.command(name='setchannel', description='Imposta il canale di verifica')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(channel='Canale da usare per la verifica')
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        ver_cfg = self._get_verification_cfg()
        ver_cfg['channel_id'] = channel.id
        self._save_verification_cfg(ver_cfg)
        await interaction.response.send_message(f'✅ Canale di verifica impostato a {channel.mention}.', ephemeral=True)

    @verify_group.command(name='setrole', description='Imposta il ruolo assegnato alla verifica')
    @owner_or_has_permissions(manage_roles=True)
    @app_commands.describe(role='Ruolo da assegnare ai verificati', name='Nuovo nome ruolo (facoltativo)')
    async def set_role(self, interaction: discord.Interaction, role: discord.Role, name: str | None = None):
        ver_cfg = self._get_verification_cfg()
        if name:
            try:
                await role.edit(name=name, reason='Rename verify role')
            except Exception:
                pass
            ver_cfg['role_name'] = name
        ver_cfg['role_id'] = role.id
        self._save_verification_cfg(ver_cfg)
        await interaction.response.send_message(f'✅ Ruolo di verifica impostato: {role.mention}.', ephemeral=True)

    @verify_group.command(name='panel', description='Invia o sostituisce il pannello di verifica nel canale configurato')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(replace='Se vero, sostituisce il pannello precedente', text='Testo sopra il bottone')
    async def send_panel(self, interaction: discord.Interaction, replace: bool = False, text: str | None = None):
        ver_cfg = self._get_verification_cfg()
        channel_id = ver_cfg.get('channel_id')
        if not channel_id:
            await interaction.response.send_message('❌ Nessun canale configurato. Usa /verify setchannel.', ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(channel_id))
        if channel is None:
            await interaction.response.send_message('❌ Il canale configurato non esiste più.', ephemeral=True)
            return
        if text:
            ver_cfg['panel_text'] = text
            self._save_verification_cfg(ver_cfg)
        await self._send_panel(channel, replace=replace)
        await interaction.response.send_message('✅ Pannello inviato.', ephemeral=True)

    @verify_group.command(name='forceverify', description='Verifica forzatamente un utente assegnando il ruolo')
    @owner_or_has_permissions(manage_roles=True)
    @app_commands.describe(member='Utente da verificare')
    async def force_verify(self, interaction: discord.Interaction, member: discord.Member):
        ver_cfg = self._get_verification_cfg()
        role_id = ver_cfg.get('role_id')
        role = None
        if role_id:
            role = interaction.guild.get_role(int(role_id))
        if role is None:
            # fallback name search
            role = discord.utils.get(interaction.guild.roles, name=ver_cfg.get('role_name', 'Verified'))
        if role is None:
            role = await interaction.guild.create_role(name=ver_cfg.get('role_name', 'Verified'), reason='Create verify role')
            ver_cfg['role_id'] = role.id
            self._save_verification_cfg(ver_cfg)
        try:
            await member.add_roles(role, reason='Force verify')
            await interaction.response.send_message(f'✅ {member.mention} verificato.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ Errore: {e}', ephemeral=True)

    @verify_group.command(name='remove', description='Rimuove il ruolo di verifica da un utente')
    @owner_or_has_permissions(manage_roles=True)
    @app_commands.describe(member='Utente da rimuovere dalla verifica')
    async def remove_verify(self, interaction: discord.Interaction, member: discord.Member):
        ver_cfg = self._get_verification_cfg()
        role_id = ver_cfg.get('role_id')
        role = None
        if role_id:
            role = interaction.guild.get_role(int(role_id))
        if role is None:
            role = discord.utils.get(interaction.guild.roles, name=ver_cfg.get('role_name', 'Verified'))
        if role is None:
            await interaction.response.send_message('❌ Ruolo di verifica non trovato.', ephemeral=True)
            return
        try:
            await member.remove_roles(role, reason='Remove verify')
            await interaction.response.send_message(f'✅ Rimosso ruolo verifica da {member.mention}.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ Errore: {e}', ephemeral=True)

    @verify_group.command(name='config', description='Mostra la configurazione verifica corrente')
    async def show_config(self, interaction: discord.Interaction):
        ver_cfg = self._get_verification_cfg()
        channel_id = ver_cfg.get('channel_id')
        role_id = ver_cfg.get('role_id')
        message_id = ver_cfg.get('message_id')
        auto = ver_cfg.get('auto_resend', False)
        panel_text = ver_cfg.get('panel_text', 'Clicca il bottone per verificarti!')
        lines = [
            f'Canale: {f"<#{channel_id}>" if channel_id else "Non impostato"}',
            f'Ruolo: {f"<@&{role_id}>" if role_id else "Non impostato"}',
            f'Messaggio pannello ID: {message_id or "N/D"}',
            f'Auto resend: {"Attivo" if auto else "Disattivo"}',
            f'Testo pannello: {panel_text[:80] + ("..." if len(panel_text) > 80 else "")}'
        ]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    @verify_group.command(name='autoresend', description='Attiva/Disattiva la reinvio automatico del pannello a restart')
    @owner_or_has_permissions(administrator=True)
    @app_commands.describe(enabled='True/False')
    async def autoresend(self, interaction: discord.Interaction, enabled: bool):
        ver_cfg = self._get_verification_cfg()
        ver_cfg['auto_resend'] = enabled
        self._save_verification_cfg(ver_cfg)
        await interaction.response.send_message(f'✅ Auto resend impostato a {enabled}.', ephemeral=True)

async def setup(bot):
    await bot.add_cog(Verify(bot))
