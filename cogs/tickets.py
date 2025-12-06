import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import html as htmlescape
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(__file__)
TICKETS_FILE = os.path.join(BASE_DIR, '..', 'tickets.json')
CONFIG_FILE = os.path.join(BASE_DIR, '..', 'config_tickets.json')
TRANSCRIPTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "transcripts")

# ------------------ CONFIG AUTOMATICA PREMIUM ------------------
DEFAULT_AUTO_CONFIG = {
    "staff_role_id": 123456789012345678,
    "category_id": None,
    "panels": [

        {
            "name": "Bug & Supporto",
            "emoji": "<a:Attenzione:1441165315726905456>",
            "description": "Segnala bug o richiedi assistenza tecnica in modo dettagliato.",
            "color": 16711680,
            "image": "https://cdn.discordapp.com/attachments/773466149249613824/1446925387383832769/alice_banner.webp",
            "category": "Tickets – Bug & Supporto",
            "fields": [
                {
                    "name": "Tipo di richiesta",
                    "placeholder": "Bug / Assistenza / Altro",
                    "required": True
                },
                {
                    "name": "Descrizione del problema",
                    "placeholder": "Spiega dettagliatamente cosa sta succedendo.",
                    "required": True
                },
                {
                    "name": "Come riprodurlo (se bug)",
                    "placeholder": "1. ... 2. ... 3. ... (opzionale)",
                    "required": False
                }
            ]
        },

        {
            "name": "Richiesta CW",
            "emoji": "<:Spade:1406304639326097408>",
            "description": "Richiedi CW: controlli, attivazioni o autorizzazioni.",
            "color": 65280,
            "image": "https://cdn.discordapp.com/attachments/773466149249613824/1446925387383832769/alice_banner.webp",
            "category": "Tickets – CW",
            "fields": [
                {
                    "name": "Motivo della richiesta",
                    "placeholder": "Perché richiedi il CW?",
                    "required": True
                },
                {
                    "name": "ID Utente / Riferimento",
                    "placeholder": "Inserisci eventuali ID o riferimenti (opzionale)",
                    "required": False
                }
            ]
        },

        {
            "name": "Richiesta Mod DS",
            "emoji": "<:ModDiscord:1406397342914973888>",
            "description": "Richiedi interventi o modifiche relativi a DS.",
            "color": 16711680,
            "image": "https://cdn.discordapp.com/attachments/773466149249613824/1446925387383832769/alice_banner.webp",
            "category": "Tickets – Mod DS",
            "fields": [
                {
                    "name": "Tipo di richiesta",
                    "placeholder": "Modifica / Assistenza / Altro",
                    "required": True
                },
                {
                    "name": "Dettagli",
                    "placeholder": "Spiega in modo chiaro cosa ti serve.",
                    "required": True
                }
            ]
        },

        {
            "name": "Richiesta Alicers",
            "emoji": "<a:Corona:1406397702610227240>",
            "description": "Richiedi interventi o modifiche riguardanti gli Alicers.",
            "color": 16711935,
            "image": "https://cdn.discordapp.com/attachments/773466149249613824/1446925387383832769/alice_banner.webp",
            "category": "Tickets – Alicers",
            "fields": [
                {
                    "name": "Descrizione richiesta",
                    "placeholder": "Quale intervento desideri dagli Alicers?",
                    "required": True
                },
                {
                    "name": "Priorità",
                    "placeholder": "Bassa / Media / Alta",
                    "required": False
                }
            ]
        }
    ]
}

def load_or_create_config():
    if not os.path.exists(CONFIG_FILE):
        save_json(CONFIG_FILE, DEFAULT_AUTO_CONFIG)
        return DEFAULT_AUTO_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('config malformed')
        merged = {**DEFAULT_AUTO_CONFIG, **data}
        if 'panels' not in merged or not isinstance(merged['panels'], list):
            merged['panels'] = DEFAULT_AUTO_CONFIG['panels']
        save_json(CONFIG_FILE, merged)
        return merged
    except Exception:
        save_json(CONFIG_FILE, DEFAULT_AUTO_CONFIG)
        return DEFAULT_AUTO_CONFIG

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def ensure_transcripts_dir():
    try:
        os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    except Exception:
        pass

# ------------------ Modal & Views ------------------
class TicketFormModal(ui.Modal):
    def __init__(self, panel, cog):
        super().__init__(title=panel.get('name', 'Modulo Ticket'))
        self.panel = panel
        self.cog = cog
        for field in panel.get('fields', [])[:5]:
            style = discord.TextStyle.paragraph if len(field.get('name', '')) > 20 else discord.TextStyle.short
            self.add_item(ui.TextInput(
                label=field.get('name', 'Campo'),
                placeholder=field.get('placeholder', ''),
                required=field.get('required', True),
                style=style
            ))

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"📋 Informazioni Ticket — {self.panel.get('name')}",
            color=self.panel.get('color', 0xE6C44C),
            timestamp=datetime.utcnow()
        )
        for i, child in enumerate(self.children):
            fname = self.panel.get('fields', [])[i].get('name', f'Campo {i+1}') if i < len(self.panel.get('fields', [])) else f'Campo {i+1}'
            embed.add_field(name=fname, value=child.value or "—", inline=False)

        if self.panel.get('image'):
            embed.set_image(url=self.panel['image'])

        try:
            await interaction.response.send_message("✅ Informazioni registrate!", ephemeral=True)
        except:
            try:
                await interaction.followup.send("✅ Informazioni registrate!", ephemeral=True)
            except:
                pass

        try:
            if interaction.channel:
                await interaction.channel.send(embed=embed)
        except:
            pass

class TicketFormView(ui.View):
    def __init__(self, modal: TicketFormModal):
        super().__init__(timeout=None)
        self.modal = modal

    @ui.button(label="Compila Informazioni", style=discord.ButtonStyle.success, custom_id="open_modal_button")
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(self.modal)

class TranscriptButton(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="📄 Transcript", style=discord.ButtonStyle.blurple, custom_id="ticket_transcript_btn")
    async def transcript(self, interaction: discord.Interaction, button: ui.Button):
        if not any(r.id in self.cog.config.get("staff_role_id", []) for r in interaction.user.roles) and not interaction.user.guild_permissions.administrator:
            try:
                await interaction.response.send_message("❌ Solo lo staff può usare questo pulsante.", ephemeral=True)
            except:
                pass
            return
        await self.cog.generate_transcript(interaction, invoked_by="button")

class TicketPanelButton(ui.Button):
    def __init__(self, panel, cog):
        label = panel.get('name', 'Ticket')
        emoji = panel.get('emoji', None)
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.primary,
                         custom_id=f"ticket_panel_{panel.get('name','panel').lower().replace(' ', '_')}")
        self.panel = panel
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Errore: comando non eseguibile qui.", ephemeral=True)
            return

        category = await self.cog._resolve_ticket_category(guild, panel=self.panel)
        if category is None:
            await interaction.followup.send("❌ Categoria ticket configurata non trovata. Contatta lo staff per verificare l'ID nel file di configurazione.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        staff_role_id = self.cog.config.get("staff_role_id")
        if staff_role_id:
            staff_role = guild.get_role(staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel_name = f"ticket-{interaction.user.name.lower()}-{len(self.cog.tickets) + 1}"
        try:
            ticket_channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        except Exception as e:
            await interaction.followup.send(f"❌ Errore nella creazione del canale ticket: {e}", ephemeral=True)
            return

        ticket_id = str(ticket_channel.id)
        self.cog.tickets[ticket_id] = {
            'author': interaction.user.id,
            'panel': self.panel.get('name'),
            'created_at': datetime.utcnow().isoformat(),
            'members': [interaction.user.id],
            'status': 'open'
        }
        self.cog.save_tickets()

        embed = discord.Embed(
            title=f"🎟️ Ticket: {self.panel.get('name')}",
            description=self.panel.get('description', ''),
            color=self.panel.get('color', 0xE6C44C)
        )
        embed.add_field(name="ID Ticket", value=ticket_id, inline=False)
        embed.add_field(name="Richiedente", value=interaction.user.mention, inline=False)
        embed.set_footer(text="Usa /ticket close per chiudere il ticket")

        if self.panel.get('image'):
            embed.set_image(url=self.panel['image'])

        try:
            transcript_view = TranscriptButton(self.cog)
            await ticket_channel.send(embed=embed, view=transcript_view)
            if self.panel.get('fields'):
                modal = TicketFormModal(self.panel, self.cog)
                view = TicketFormView(modal)
                await ticket_channel.send("Premi il pulsante per compilare le informazioni del ticket:", view=view)
        except:
            pass

        await interaction.followup.send(f"✅ Ticket creato: {ticket_channel.mention}", ephemeral=True)

class TicketPanelsView(ui.View):
    def __init__(self, panels, cog):
        super().__init__(timeout=None)
        for panel in panels:
            self.add_item(TicketPanelButton(panel, cog))


# ------------------ Cog ------------------
class Tickets(commands.Cog):
    """Cog che gestisce il sistema tickets (slash + comandi classici)"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tickets = load_json(TICKETS_FILE, {})
        self.config = load_or_create_config()
        ensure_transcripts_dir()

        self.ticket_group = app_commands.Group(name="ticket", description="Gestione tickets")
        self.ticket_group.command(name="panel", description="Mostra il pannello per creare ticket")(self.ticket_panel)
        self.ticket_group.command(name="create", description="Crea un nuovo ticket")(self.create_ticket)
        self.ticket_group.command(name="close", description="Chiude il ticket nel canale attuale")(self.close_ticket)
        self.ticket_group.command(name="reopen", description="Riapri un ticket chiuso (solo staff)")(self.reopen_ticket)
        self.ticket_group.command(name="delete", description="Elimina definitivamente il ticket (solo staff)")(self.delete_ticket)
        try:
            self.bot.tree.add_command(self.ticket_group)
        except Exception:
            pass

    def save_tickets(self):
        save_json(TICKETS_FILE, self.tickets)

    async def _resolve_ticket_category(self, guild: discord.Guild, panel: Optional[dict] = None) -> Optional[discord.CategoryChannel]:
        category_id = self.config.get("category_id")
        category: Optional[discord.CategoryChannel] = None
        if category_id:
            try:
                category = guild.get_channel(int(category_id))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                category = None
            if category is not None and not isinstance(category, discord.CategoryChannel):
                category = None
            if category is None:
                return None
            return category

        category_name = None
        if panel:
            category_name = panel.get('category')
        if not category_name:
            category_name = self.config.get("category_name") or "Tickets"

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            try:
                category = await guild.create_category(category_name)
            except Exception:
                return None
        return category

    async def generate_transcript(self, interaction: discord.Interaction, invoked_by: str = "unknown"):
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

        channel = interaction.channel
        if channel is None:
            try:
                await interaction.followup.send("❌ Impossibile leggere il canale.", ephemeral=True)
            except:
                pass
            return

        channel_id = str(channel.id)
        if channel_id not in self.tickets:
            try:
                await interaction.followup.send("❌ Questo non è un canale ticket!", ephemeral=True)
            except:
                pass
            return

        ticket = self.tickets[channel_id]
        author_id = ticket.get('author')

        txt_lines = []
        txt_lines.append(f"===== TRANSCRIPT TICKET {channel.name} =====")
        txt_lines.append(f"Server: {channel.guild.name} ({channel.guild.id})")
        creator = channel.guild.get_member(author_id)
        txt_lines.append(f"Creato da: {creator} ({author_id})")
        txt_lines.append(f"Aperto il: {ticket.get('created_at')}")
        txt_lines.append(f"Generato da: {interaction.user} (modo: {invoked_by})")
        txt_lines.append("")
        txt_lines.append("----- MESSAGGI -----")

        html_parts = []
        html_parts.append("<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
        html_parts.append(f"<title>Transcript {htmlescape.escape(channel.name)}</title>")
        html_parts.append("<style>")
        html_parts.append(f"body{{background:#0f0f0f;color:#ffffff;font-family:Segoe UI,Arial,Helvetica,sans-serif;padding:18px}}")
        html_parts.append(".wrap{max-width:980px;margin:0 auto}")
        html_parts.append(".header{background:#1a1a1a;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.5);margin-bottom:14px}")
        html_parts.append(".server{color:#bbbbbb;font-size:13px}")
        html_parts.append(".title{font-size:18px;color:#ffffff;margin-bottom:6px}")
        html_parts.append(".msg{background:#111214;border-radius:8px;padding:10px;margin:10px 0;border:1px solid rgba(255,255,255,0.02)}")
        html_parts.append(".meta{font-size:12px;color:#9aa3b2;margin-bottom:6px}")
        html_parts.append(".content{white-space:pre-wrap;color:#d5dbe5}")
        html_parts.append(".embed{border-left:4px solid #f1d37a;background:#101214;padding:8px;margin-top:6px;border-radius:6px}")
        html_parts.append(".attach{font-size:13px;margin-top:6px;color:#9aa3b2}")
        html_parts.append("</style></head><body><div class='wrap'>")
        html_parts.append("<div class='header'>")
        html_parts.append(f"<div class='title'>📄 Transcript — {htmlescape.escape(channel.guild.name)}</div>")
        html_parts.append(f"<div class='server'>Canale: {htmlescape.escape(channel.name)}</div>")
        html_parts.append(f"<div class='server'>Creato da: {htmlescape.escape(str(creator))} ({author_id})</div>")
        html_parts.append(f"<div class='server'>Aperto il: {htmlescape.escape(str(ticket.get('created_at')))}</div>")
        html_parts.append(f"<div class='server'>Generato da: {htmlescape.escape(str(interaction.user))} (modo: {htmlescape.escape(invoked_by)})</div>")
        html_parts.append("</div>")

        try:
            async for msg in channel.history(limit=None, oldest_first=True):
                ts = msg.created_at.strftime("%d %b %Y • %H:%M:%S")
                author_display = f"{htmlescape.escape(str(msg.author))} ({msg.author.id})"
                content_text = msg.content or ""
                if content_text.strip():
                    txt_lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content_text}")
                else:
                    txt_lines.append(f"[{ts}] {msg.author} ({msg.author.id}): <Nessun testo>")

                html_parts.append("<div class='msg'>")
                html_parts.append(f"<div class='meta'><strong>{author_display}</strong> • <span>{ts}</span></div>")
                if content_text.strip():
                    html_parts.append(f"<div class='content'>{htmlescape.escape(content_text)}</div>")
                else:
                    html_parts.append("<div class='content'><i>&lt;Nessun testo&gt;</i></div>")

                if msg.embeds:
                    for emb in msg.embeds:
                        try:
                            html_parts.append("<div class='embed'>")
                            if getattr(emb, "title", None):
                                html_parts.append(f"<div><strong>{htmlescape.escape(emb.title)}</strong></div>")
                            if getattr(emb, "description", None) and emb.description:
                                html_parts.append(f"<div>{htmlescape.escape((emb.description or '')[:3000])}</div>")
                            if getattr(emb, "fields", None):
                                for field in emb.fields:
                                    html_parts.append(f"<div><em>{htmlescape.escape(field.name)}</em>: {htmlescape.escape(field.value)}</div>")
                            if getattr(emb, "footer", None) and emb.footer.text:
                                html_parts.append(f"<div class='meta'>Footer: {htmlescape.escape(emb.footer.text)}</div>")
                            html_parts.append("</div>")
                        except:
                            html_parts.append("<div class='embed'><em>Embed: errore nel parsing</em></div>")

                if msg.attachments:
                    for att in msg.attachments:
                        try:
                            txt_lines.append(f"    [ALLEGATO] {att.filename} -> {att.url}")
                            html_parts.append(f"<div class='attach'>📎 <a href='{htmlescape.escape(att.url)}' target='_blank'>{htmlescape.escape(att.filename)}</a></div>")
                        except:
                            html_parts.append("<div class='attach'><em>Allegato (errore)</em></div>")

                html_parts.append("</div>")
        except Exception as e:
            txt_lines.append(f"[ERRORE LETTURA MESSAGGI: {e}]")
            html_parts.append(f"<div class='msg'><em>Errore lettura messaggi: {htmlescape.escape(str(e))}</em></div>")

        html_parts.append("</div></body></html>")

        transcript_text = "\n".join(txt_lines)
        transcript_html = "\n".join(html_parts)

        ensure_transcripts_dir()

        safe_name = channel.name.replace(" ", "_")
        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        txt_filename = f"transcript_{safe_name}_{channel.id}_{timestamp_str}.txt"
        html_filename = f"transcript_{safe_name}_{channel.id}_{timestamp_str}.html"
        txt_path = os.path.join(TRANSCRIPTS_DIR, txt_filename)
        html_path = os.path.join(TRANSCRIPTS_DIR, html_filename)

        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)
        except:
            txt_path = None

        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(transcript_html)
        except:
            html_path = None

        log_channel = None
        log_ch_id = self.config.get("log_channel_id")
        if log_ch_id:
            try:
                log_channel = channel.guild.get_channel(log_ch_id)
            except:
                log_channel = self.bot.get_channel(log_ch_id)

        log_msg = f"📄 Transcript del ticket `{channel.name}` (invocato da {interaction.user.mention}, modo: {invoked_by})"

        if log_channel:
            try:
                files = []
                if html_path:
                    files.append(discord.File(html_path, filename=html_filename))
                if txt_path:
                    files.append(discord.File(txt_path, filename=txt_filename))
                if files:
                    await log_channel.send(content=log_msg, files=files)
                else:
                    await log_channel.send(content=log_msg + "\n```" + (transcript_text[:1900] or "Nessun contenuto") + "```")
            except:
                try:
                    await interaction.followup.send("⚠️ Non sono riuscito a inviare il transcript nel canale log (permessi?).", ephemeral=True)
                except:
                    pass
        else:
            try:
                await interaction.followup.send("⚠️ Canale di log non trovato; transcript salvato localmente.", ephemeral=True)
            except:
                pass

        try:
            author_member = channel.guild.get_member(author_id)
            if author_member:
                files = []
                if html_path:
                    files.append(discord.File(html_path, filename=html_filename))
                if txt_path:
                    files.append(discord.File(txt_path, filename=txt_filename))
                if files:
                    await author_member.send(content=f"📄 Transcript del tuo ticket `{channel.name}` (richiesto da {interaction.user}):", files=files)
                else:
                    await author_member.send(content=f"📄 Transcript del tuo ticket `{channel.name}` (richiesto da {interaction.user}):\n```{transcript_text[:1900]}```")
        except:
            pass

        try:
            await interaction.followup.send("📄 Transcript generato e salvato in /transcripts/ (inviato a log + DM se possibile).", ephemeral=True)
        except:
            pass

    # ---------- Slash commands (app commands) ----------

    async def ticket_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        panels = self.config.get("panels", [])
        if not panels:
            await interaction.followup.send("❌ Nessun pannello configurato.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎟️ Pannelli Ticket",
            description="Clicca su un pulsante per aprire un ticket:",
            color=0xE6C44C
        )
        for panel in panels:
            emoji = panel.get("emoji", None)
            name = panel.get("name", "Ticket")
            desc = panel.get("description", "")
            embed.add_field(name=f"{emoji} {name}" if emoji else name, value=desc, inline=False)

        view = TicketPanelsView(panels, self)
        try:
            await interaction.followup.send(embed=embed, view=view)
        except:
            try:
                await interaction.channel.send(embed=embed, view=view)
            except:
                await interaction.followup.send("❌ Impossibile inviare il pannello.", ephemeral=True)

    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        await interaction.response.defer()
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Errore: comando non eseguibile qui.", ephemeral=True)
            return

        category = await self._resolve_ticket_category(guild)
        if category is None:
            await interaction.followup.send("❌ Categoria ticket configurata non trovata. Contatta lo staff per verificare l'ID nel file di configurazione.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        staff_role_id = self.config.get("staff_role_id")
        if staff_role_id:
            staff_role = guild.get_role(staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel_name = f"ticket-{interaction.user.name.lower()}-{len(self.tickets) + 1}"
        try:
            ticket_channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        except Exception as e:
            await interaction.followup.send(f"❌ Errore nella creazione del canale ticket: {e}", ephemeral=True)
            return

        ticket_id = str(ticket_channel.id)
        self.tickets[ticket_id] = {
            'author': interaction.user.id,
            'topic': topic,
            'created_at': datetime.utcnow().isoformat(),
            'members': [interaction.user.id],
            'status': 'open'
        }
        self.save_tickets()

        embed = discord.Embed(
            title=f"🎟️ Ticket: {topic}",
            description=f"Ticket creato da {interaction.user.mention}",
            color=0xE6C44C
        )
        embed.add_field(name="ID Ticket", value=ticket_id, inline=False)
        embed.add_field(name="Data Creazione", value=datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S"), inline=False)
        embed.set_footer(text="Usa /ticket close per chiudere il ticket")

        try:
            transcript_view = TranscriptButton(self)
            await ticket_channel.send(embed=embed, view=transcript_view)
            await interaction.followup.send(f"✅ Ticket creato: {ticket_channel.mention}", ephemeral=True)
        except:
            await interaction.followup.send(f"✅ Ticket creato: {ticket_channel.mention}", ephemeral=True)

    async def close_ticket(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except:
            pass

        channel_id = str(interaction.channel.id)
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!", ephemeral=True)
            return

        ticket = self.tickets[channel_id]
        staff_role_id = self.config.get("staff_role_id")
        staff_role = interaction.guild.get_role(staff_role_id) if staff_role_id else None
        is_staff = staff_role in interaction.user.roles if staff_role else False

        if interaction.user.id != ticket['author'] and not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo l'autore, lo staff o un admin può chiudere questo ticket!", ephemeral=True)
            return

        ticket['status'] = 'closed'
        self.save_tickets()

        author_member = interaction.guild.get_member(ticket['author'])
        if author_member:
            try:
                await interaction.channel.set_permissions(author_member, read_messages=True, send_messages=False)
            except:
                pass

        embed = discord.Embed(
            title="🔒 Ticket Chiuso",
            description=f"Il ticket è stato chiuso da {interaction.user.mention}\nIl canale rimane visibile ma non puoi scrivere nuovi messaggi.",
            color=0x888888
        )

        try:
            await interaction.followup.send("✅ Ticket chiuso.", ephemeral=True)
        except:
            try:
                await interaction.channel.send("✅ Ticket chiuso.")
            except:
                pass

        try:
            await interaction.channel.send(embed=embed)
        except:
            pass

    async def reopen_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer()
        channel_id = str(interaction.channel.id)
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!", ephemeral=True)
            return

        ticket = self.tickets[channel_id]
        staff_role_id = self.config.get("staff_role_id")
        staff_role = interaction.guild.get_role(staff_role_id) if staff_role_id else None
        is_staff = staff_role in interaction.user.roles if staff_role else False

        if not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo lo staff o un admin può riaprire i ticket!", ephemeral=True)
            return

        if ticket.get('status') != 'closed':
            await interaction.followup.send("❌ Questo ticket non è chiuso!", ephemeral=True)
            return

        ticket['status'] = 'open'
        self.save_tickets()

        author = interaction.guild.get_member(ticket['author'])
        if author:
            try:
                await interaction.channel.set_permissions(author, read_messages=True, send_messages=True)
            except:
                pass

        embed = discord.Embed(
            title="🔓 Ticket Riaperto",
            description=f"Il ticket è stato riaperto da {interaction.user.mention}\nPuoi scrivere nuovi messaggi.",
            color=0xE6C44C
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.channel.send("✅ Ticket riaperto.")
            except:
                pass

        try:
            await interaction.channel.send(embed=embed)
        except:
            pass

    async def delete_ticket(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

        channel = interaction.channel
        if channel is None:
            await interaction.followup.send("❌ Impossibile eliminare: canale non valido.", ephemeral=True)
            return

        channel_id = str(channel.id)
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!", ephemeral=True)
            return

        ticket = self.tickets[channel_id]
        staff_role_id = self.config.get("staff_role_id")
        staff_role = channel.guild.get_role(staff_role_id) if staff_role_id else None
        is_staff = staff_role in interaction.user.roles if staff_role else False

        if not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo lo staff o un admin può eliminare i ticket!", ephemeral=True)
            return

        try:
            await self.generate_transcript(interaction, invoked_by="delete")
        except:
            try:
                await interaction.followup.send("⚠️ Errore durante la generazione del transcript; procedo comunque con l'eliminazione.", ephemeral=True)
            except:
                pass

        try:
            del self.tickets[channel_id]
            self.save_tickets()
        except:
            pass

        try:
            await channel.delete(reason=f"Ticket eliminato da {interaction.user}")
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Errore eliminazione canale: {e}", ephemeral=True)
            except:
                pass
            return

        try:
            await interaction.followup.send("🗑️ Ticket eliminato.", ephemeral=True)
        except:
            pass

    @commands.command(name="add_member")
    @commands.has_permissions(manage_channels=True)
    async def add_member(self, ctx: commands.Context, member: discord.Member):
        channel_id = str(ctx.channel.id)
        if channel_id not in self.tickets:
            await ctx.send("❌ Questo non è un canale ticket!")
            return

        ticket = self.tickets[channel_id]
        if ctx.author.id != ticket['author'] and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Solo l'autore del ticket o un admin può aggiungere utenti!")
            return

        if member.id in ticket.get('members', []):
            await ctx.send("❌ Questo utente è già nel ticket!")
            return

        ticket.setdefault('members', []).append(member.id)
        self.save_tickets()
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"✅ {member.mention} è stato aggiunto al ticket.")

    @commands.command(name="remove_member")
    @commands.has_permissions(manage_channels=True)
    async def remove_member(self, ctx: commands.Context, member: discord.Member):
        channel_id = str(ctx.channel.id)
        if channel_id not in self.tickets:
            await ctx.send("❌ Questo non è un canale ticket!")
            return

        ticket = self.tickets[channel_id]
        if ctx.author.id != ticket['author'] and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Solo l'autore del ticket o un admin può rimuovere utenti!")
            return

        if member.id not in ticket.get('members', []):
            await ctx.send("❌ Questo utente non è nel ticket!")
            return

        ticket['members'].remove(member.id)
        self.save_tickets()
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✅ {member.mention} è stato rimosso dal ticket.")

    @commands.command(name="list_tickets")
    async def list_tickets(self, ctx: commands.Context):
        user_tickets = [(tid, t) for tid, t in self.tickets.items() if t.get('author') == ctx.author.id and t.get('status') == 'open']
        if not user_tickets:
            await ctx.send("❌ Non hai ticket aperti!")
            return

        embed = discord.Embed(title="I Tuoi Ticket Aperti", description=f"Totale: {len(user_tickets)}", color=0xE6C44C)
        for ticket_id, ticket in user_tickets:
            channel = ctx.guild.get_channel(int(ticket_id))
            created_date = datetime.fromisoformat(ticket.get('created_at')).strftime("%d/%m/%Y %H:%M")
            embed.add_field(name=f"{ticket.get('panel', 'Ticket')}", value=f"ID: {ticket_id}\nCreato: {created_date}\nCanale: {channel.mention if channel else 'Non trovato'}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="ticket_help")
    async def ticket_help(self, ctx: commands.Context):
        embed = discord.Embed(title="Sistema Tickets", description="Usa i comandi seguenti:", color=0xE6C44C)
        embed.add_field(name="/ticket create <argomento>", value="Crea un nuovo ticket", inline=False)
        embed.add_field(name="/ticket panel", value="Mostra il pannello per creare ticket", inline=False)
        embed.add_field(name="/ticket close", value="Chiude il ticket nel canale attuale", inline=False)
        embed.add_field(name="/ticket reopen", value="Riapri un ticket chiuso (solo staff)", inline=False)
        embed.add_field(name="/ticket delete", value="Elimina il ticket (solo staff)", inline=False)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
