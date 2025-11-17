import discord
from discord.ext import commands
from discord import app_commands, ui
from datetime import datetime
import json
import os
import asyncio
import glob

from bot_utils import owner_or_has_permissions, is_owner

# Stampa tutti i file .json ricorsivamente
json_files = glob.glob("**/*.json", recursive=True)
print(json_files)

class TicketFormModal(ui.Modal):
    def __init__(self, panel_data, cog):
        super().__init__(title=f"Informazioni - {panel_data['name']}")
        self.panel_data = panel_data
        self.cog = cog
        
        # Aggiungi campi dinamicamente
        for field in panel_data.get('fields', [])[:5]:  # Max 5 campi per modal
            self.add_item(ui.TextInput(
                label=field['name'],
                placeholder=field.get('placeholder', ''),
                required=True,
                style=discord.TextStyle.paragraph if len(field['name']) > 20 else discord.TextStyle.short
            ))
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Crea l'embed con le informazioni inserite
        embed = discord.Embed(
            title=f"📋 Informazioni Ticket - {self.panel_data['name']}",
            color=self.panel_data['color'],
            timestamp=datetime.now()
        )
        
        # Aggiungi l'immagine
        if self.panel_data.get('image'):
            embed.set_image(url=self.panel_data['image'])
        
        # Aggiungi i campi compilati
        for i, text_input in enumerate(self.children):
            field_name = self.panel_data['fields'][i]['name'] if i < len(self.panel_data['fields']) else f"Campo {i+1}"
            embed.add_field(name=field_name, value=text_input.value, inline=False)
        
        embed.set_footer(text=f"Ticket di {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ Informazioni registrate!", ephemeral=True)

class TicketPanelButton(discord.ui.Button):
    def __init__(self, panel_data, cog):
        super().__init__(
            label=panel_data['name'],
            emoji=panel_data['emoji'],
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_panel_{panel_data['name'].lower().replace(' ', '_')}"
        )
        self.panel_data = panel_data
        self.cog = cog
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Verifica se esiste la categoria Tickets
        category_obj = discord.utils.get(interaction.guild.categories, name="Tickets")
        if not category_obj:
            try:
                category_obj = await interaction.guild.create_category("Tickets")
            except Exception as e:
                await interaction.followup.send(f"❌ Errore nella creazione della categoria: {e}", ephemeral=True)
                return
        
        # Crea il canale del ticket
        channel_name = f"ticket-{interaction.user.name.lower()}-{len(self.cog.tickets) + 1}"
        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Aggiungi il ruolo staff se configurato
            staff_role_id = self.cog.config.get("staff_role_id")
            if staff_role_id:
                staff_role = interaction.guild.get_role(staff_role_id)
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            ticket_channel = await category_obj.create_text_channel(
                channel_name,
                overwrites=overwrites
            )
            
            # Salva le informazioni del ticket
            ticket_id = str(ticket_channel.id)
            self.cog.tickets[ticket_id] = {
                'author': interaction.user.id,
                'panel': self.panel_data['name'],
                'created_at': datetime.now().isoformat(),
                'status': 'open'
            }
            self.cog.save_tickets()
            
            # Invia il messaggio di benvenuto
            embed = discord.Embed(
                title=f"🎟️ Ticket: {self.panel_data['name']}",
                description=self.panel_data['description'],
                color=self.panel_data['color']
            )
            
            if self.panel_data.get('image'):
                embed.set_image(url=self.panel_data['image'])
            
            embed.add_field(name="ID Ticket", value=ticket_id, inline=False)
            embed.add_field(name="Richiedente", value=interaction.user.mention, inline=False)
            embed.set_footer(text="Usa /ticket close per chiudere il ticket")
            
            await ticket_channel.send(embed=embed)
            
            # Taglia i ruoli in base al tipo di pannello
            panel_name = self.panel_data['name']
            mentions = [interaction.user.mention]
            
            if panel_name == "Supporto Discord":
                role_id = self.cog.config.get("roles", {}).get("discord_mod")
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        mentions.append(role.mention)
            
            elif panel_name == "Richiesta CW":
                role_id = self.cog.config.get("roles", {}).get("cw_manager")
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        mentions.append(role.mention)
            
            elif panel_name == "Join Clan":
                for role_name in ["mod", "co_leader", "leader"]:
                    role_id = self.cog.config.get("roles", {}).get(role_name)
                    if role_id:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            mentions.append(role.mention)
            
            # Invia il messaggio con i tag
            if len(mentions) > 1:
                tag_message = " ".join(mentions)
                await ticket_channel.send(f"📢 {tag_message}", allowed_mentions=discord.AllowedMentions(roles=True))
            
            # Mostra il form modale automaticamente
            modal = TicketFormModal(self.panel_data, self.cog)
            
            # Attendi un po' per assicurarti che l'interazione sia completata
            await asyncio.sleep(0.5)
            
            # Crea un embed di istruzioni
            instr_embed = discord.Embed(
                title="📝 Compila le Informazioni",
                description="Clicca il bottone sottostante per aprire il modulo di compilazione",
                color=0x3498DB
            )
            
            # Crea il pulsante per compilare il form
            button = discord.ui.Button(label="Compila Informazioni", style=discord.ButtonStyle.success)
            
            async def modal_callback(button_interaction: discord.Interaction):
                await button_interaction.response.send_modal(modal)
            
            button.callback = modal_callback
            view = discord.ui.View(timeout=None)
            view.add_item(button)
            
            await ticket_channel.send(embed=instr_embed, view=view)
            await interaction.followup.send(f"✅ Ticket creato: {ticket_channel.mention}", ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ Errore nella creazione del ticket: {e}", ephemeral=True)

class TicketPanelsView(discord.ui.View):
    def __init__(self, panels, cog):
        super().__init__(timeout=None)
        self.panels = panels
        self.cog = cog
        
        for panel in panels:
            self.add_item(TicketPanelButton(panel, cog))

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tickets_file = 'tickets.json'
        self.load_tickets()
        self.load_config()

    def load_tickets(self):
        """Carica i tickets salvati da file"""
        if os.path.exists(self.tickets_file):
            with open(self.tickets_file, 'r', encoding='utf-8') as f:
                self.tickets = json.load(f)
        else:
            self.tickets = {}

    def load_config(self):
        """Carica la configurazione dei ticket"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {"categories": []}

    def save_tickets(self):
        """Salva i tickets su file"""
        with open(self.tickets_file, 'w', encoding='utf-8') as f:
            json.dump(self.tickets, f, indent=4, ensure_ascii=False)

    def save_config(self):
        """Salva la configurazione"""
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    @commands.Cog.listener()
    async def on_ready(self):
        """Evento che si attiva quando il bot è pronto"""
        # Ricaricare il pannello salvato
        panel_msg_id = self.config.get("panel_message_id")
        panel_ch_id = self.config.get("panel_channel_id")
        
        if panel_msg_id and panel_ch_id:
            try:
                channel = self.bot.get_channel(panel_ch_id)
                if channel:
                    # Crea la view con i pulsanti
                    view = TicketPanelsView(self.config.get("panels", []), self)
                    self.bot.add_view(view)
            except Exception as e:
                print(f"Errore nel caricamento del pannello: {e}")

    ticket_group = app_commands.Group(name="ticket", description="Gestisci i tuoi tickets")

    @ticket_group.command(name="create", description="Crea un nuovo ticket")
    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        """Crea un nuovo ticket"""
        await interaction.response.defer()

        # Verifica se esiste la categoria Tickets
        category = discord.utils.get(interaction.guild.categories, name="Tickets")
        if not category:
            try:
                category = await interaction.guild.create_category("Tickets")
            except Exception as e:
                await interaction.followup.send(f"❌ Errore nella creazione della categoria: {e}")
                return

        # Crea il canale del ticket
        channel_name = f"ticket-{interaction.user.name.lower()}-{len(self.tickets) + 1}"
        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Aggiungi il ruolo staff se configurato
            staff_role_id = self.config.get("staff_role_id")
            if staff_role_id:
                staff_role = interaction.guild.get_role(staff_role_id)
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                else:
                    print(f"⚠️ Ruolo staff con ID {staff_role_id} non trovato nel server")
            else:
                print("⚠️ staff_role_id non configurato in config.json")
            
            ticket_channel = await category.create_text_channel(
                channel_name,
                overwrites=overwrites
            )

            # Salva le informazioni del ticket
            ticket_id = str(ticket_channel.id)
            self.tickets[ticket_id] = {
                'author': interaction.user.id,
                'topic': topic,
                'created_at': datetime.now().isoformat(),
                'members': [interaction.user.id],
                'status': 'open'
            }
            self.save_tickets()

            # Invia il messaggio di benvenuto nel ticket
            embed = discord.Embed(
                title=f"Ticket: {topic}",
                description=f"Ticket creato da {interaction.user.mention}",
                color=0x2ECC71
            )
            embed.add_field(name="ID Ticket", value=ticket_id, inline=False)
            embed.add_field(name="Data Creazione", value=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), inline=False)
            embed.set_footer(text="Usa /ticket close per chiudere il ticket")

            await ticket_channel.send(embed=embed)
            await interaction.followup.send(f"✅ Ticket creato: {ticket_channel.mention}")

        except Exception as e:
            await interaction.followup.send(f"❌ Errore nella creazione del ticket: {e}")

    @ticket_group.command(name="close", description="Chiude il ticket nel canale attuale")
    async def close_ticket(self, interaction: discord.Interaction):
        """Chiude il ticket nel canale attuale (rimuove i permessi di scrittura)"""
        channel_id = str(interaction.channel.id)
        
        if channel_id not in self.tickets:
            await interaction.response.send_message("❌ Questo non è un canale ticket!", ephemeral=True)
            return

        ticket = self.tickets[channel_id]
        
        # Verifica che sia l'autore o un admin/staff
        staff_role_id = self.config.get("staff_role_id")
        is_staff = False
        if staff_role_id:
            staff_role = interaction.guild.get_role(staff_role_id)
            is_staff = staff_role in interaction.user.roles if staff_role else False
        
        if interaction.user.id != ticket['author'] and not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Solo l'autore del ticket, lo staff o un admin può chiuderlo!", ephemeral=True)
            return

        # Chiudi il ticket (toglie i permessi di scrittura ma non elimina il canale)
        ticket['status'] = 'closed'
        self.save_tickets()

        # Rimuovi i permessi di scrittura al creatore del ticket
        author = interaction.guild.get_member(ticket['author'])
        if author:
            await interaction.channel.set_permissions(author, read_messages=True, send_messages=False)

        embed = discord.Embed(
            title="🔒 Ticket Chiuso",
            description=f"Il ticket è stato chiuso da {interaction.user.mention}\nIl canale rimane visibile ma non puoi scrivere nuovi messaggi.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed)
        
        # Aggiungi un messaggio nel canale
        await interaction.channel.send(embed=embed)

    @ticket_group.command(name="add", description="Aggiungi un utente al ticket")
    async def add_member(self, interaction: discord.Interaction, member: discord.Member):
        """Aggiungi un utente al ticket"""
        await interaction.response.defer()
        channel_id = str(interaction.channel.id)
        
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!")
            return

        ticket = self.tickets[channel_id]
        
        # Verifica i permessi
        if interaction.user.id != ticket['author'] and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo l'autore del ticket o un admin può aggiungere utenti!")
            return

        if member.id in ticket['members']:
            await interaction.followup.send("❌ Questo utente è già nel ticket!")
            return

        # Aggiungi l'utente
        ticket['members'].append(member.id)
        self.save_tickets()

        # Aggiorna i permessi del canale
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)

        embed = discord.Embed(
            title="Utente Aggiunto",
            description=f"{member.mention} è stato aggiunto al ticket",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=embed)

    @ticket_group.command(name="remove", description="Rimuovi un utente dal ticket")
    async def remove_member(self, interaction: discord.Interaction, member: discord.Member):
        """Rimuovi un utente dal ticket"""
        await interaction.response.defer()
        channel_id = str(interaction.channel.id)
        
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!")
            return

        ticket = self.tickets[channel_id]
        
        # Verifica i permessi
        if interaction.user.id != ticket['author'] and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo l'autore del ticket o un admin può rimuovere utenti!")
            return

        if member.id not in ticket['members']:
            await interaction.followup.send("❌ Questo utente non è nel ticket!")
            return

        # Rimuovi l'utente
        ticket['members'].remove(member.id)
        self.save_tickets()

        # Rimuovi i permessi del canale
        await interaction.channel.set_permissions(member, overwrite=None)

        embed = discord.Embed(
            title="Utente Rimosso",
            description=f"{member.mention} è stato rimosso dal ticket",
            color=0xE74C3C
        )
        await interaction.followup.send(embed=embed)

    @ticket_group.command(name="addstaff", description="Aggiungi il ruolo staff al ticket")
    @owner_or_has_permissions(administrator=True)
    async def add_staff_role(self, interaction: discord.Interaction):
        """Aggiungi il ruolo staff al ticket attuale"""
        await interaction.response.defer()
        channel_id = str(interaction.channel.id)
        
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!")
            return

        staff_role_id = self.config.get("staff_role_id")
        if not staff_role_id:
            await interaction.followup.send("❌ Ruolo staff non configurato in config.json!")
            return

        staff_role = interaction.guild.get_role(staff_role_id)
        if not staff_role:
            await interaction.followup.send("❌ Ruolo staff non trovato nel server!")
            return

        # Aggiungi i permessi al ruolo
        await interaction.channel.set_permissions(staff_role, read_messages=True, send_messages=True)

        embed = discord.Embed(
            title="Ruolo Staff Aggiunto",
            description=f"{staff_role.mention} può ora visualizzare e scrivere in questo ticket",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="list", description="Mostra tutti i tuoi ticket aperti")
    @owner_or_has_permissions(administrator=True)
    async def list_tickets(self, interaction: discord.Interaction):
        """Mostra tutti i tuoi ticket aperti"""
        await interaction.response.defer()
        user_tickets = [
            (tid, t) for tid, t in self.tickets.items() 
            if t['author'] == interaction.user.id and t['status'] == 'open'
        ]

        if not user_tickets:
            await interaction.followup.send("❌ Non hai ticket aperti!")
            return

        embed = discord.Embed(
            title="I Tuoi Ticket Aperti",
            description=f"Totale: {len(user_tickets)}",
            color=0x3498DB
        )

        for ticket_id, ticket in user_tickets:
            channel = interaction.guild.get_channel(int(ticket_id))
            if channel:
                created_date = datetime.fromisoformat(ticket['created_at']).strftime("%d/%m/%Y %H:%M")
                embed.add_field(
                    name=f"{ticket['topic']}",
                    value=f"ID: {ticket_id}\nCreato: {created_date}\nCanale: {channel.mention}",
                    inline=False
                )

        await interaction.followup.send(embed=embed)

    @ticket_group.command(name="help", description="Mostra la guida ai comandi ticket")
    async def ticket_help(self, interaction: discord.Interaction):
        """Mostra la guida ai comandi"""
        embed = discord.Embed(
            title="Sistema Tickets",
            description="Usa i comandi seguenti:",
            color=0x3498DB
        )
        embed.add_field(name="/ticket create <argomento>", value="Crea un nuovo ticket", inline=False)
        embed.add_field(name="/ticket close", value="Chiude il ticket nel canale attuale", inline=False)
        embed.add_field(name="/ticket add <utente>", value="Aggiungi un utente al ticket", inline=False)
        embed.add_field(name="/ticket remove <utente>", value="Rimuovi un utente dal ticket", inline=False)
        embed.add_field(name="/ticket list", value="Mostra tutti i tuoi ticket aperti", inline=False)
        embed.add_field(name="/ticket panel", value="Mostra il pannello per creare ticket", inline=False)
        embed.add_field(name="/ticket reopen", value="Riapri un ticket chiuso (solo staff)", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ticket_group.command(name="panel", description="Mostra il pannello per creare ticket")
    async def ticket_panel(self, interaction: discord.Interaction):
        """Mostra il pannello interattivo per creare ticket"""
        # Verifica permessi manualmente
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Solo gli admin possono eseguire questo comando!", ephemeral=True)
            return
        
        # SEMPRE defer() come prima cosa dopo il check
        await interaction.response.defer(ephemeral=True)
        
        try:
            panels = self.config.get("panels", [])
            if not panels:
                await interaction.followup.send("❌ Nessun pannello configurato in config.json!")
                return
            
            # Crea l'embed del pannello
            embed = discord.Embed(
                title="🎟️ Pannelli Ticket",
                description="Clicca su uno dei pulsanti sottostanti per creare un ticket:",
                color=0x3498DB
            )
            
            for panel in panels:
                emoji = panel.get("emoji", "📝")
                embed.add_field(
                    name=f"{emoji} {panel['name']}",
                    value=panel.get('description', 'Nessuna descrizione'),
                    inline=False
                )
            
            # Crea la view con i pulsanti
            view = TicketPanelsView(panels, self)
            
            # Invia i pannelli al canale
            channel = self.bot.get_channel(interaction.channel.id)
            if channel:
                message = await channel.send(embed=embed, view=view)
                
                # Salva le info
                self.config["panel_message_id"] = message.id
                self.config["panel_channel_id"] = channel.id
                self.save_config()
                
                await interaction.followup.send("✅ Pannelli inviati!")
            else:
                await interaction.followup.send("❌ Errore: Canale non trovato")
        
        except Exception as e:
            print(f"Errore in ticket_panel: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ Errore: {str(e)}")
            except:
                print("Impossibile inviare messaggio di errore")

    @ticket_group.command(name="reopen", description="Riapri un ticket chiuso (solo staff)")
    async def reopen_ticket(self, interaction: discord.Interaction):
        """Riapri un ticket chiuso"""
        await interaction.response.defer()
        channel_id = str(interaction.channel.id)
        
        if channel_id not in self.tickets:
            await interaction.followup.send("❌ Questo non è un canale ticket!")
            return

        ticket = self.tickets[channel_id]
        
        # Verifica che sia staff o admin
        staff_role_id = self.config.get("staff_role_id")
        is_staff = False
        if staff_role_id:
            staff_role = interaction.guild.get_role(staff_role_id)
            is_staff = staff_role in interaction.user.roles if staff_role else False
        
        if not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Solo lo staff o un admin può riaprire i ticket!")
            return
        
        if ticket['status'] != 'closed':
            await interaction.followup.send("❌ Questo ticket non è chiuso!")
            return

        # Riapri il ticket
        ticket['status'] = 'open'
        self.save_tickets()

        # Ripristina i permessi di scrittura al creatore del ticket
        author = interaction.guild.get_member(ticket['author'])
        if author:
            await interaction.channel.set_permissions(author, read_messages=True, send_messages=True)

        embed = discord.Embed(
            title="🔓 Ticket Riaperto",
            description=f"Il ticket è stato riaperto da {interaction.user.mention}\nPuoi scrivere nuovi messaggi.",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=embed)
        
        # Aggiungi un messaggio nel canale
        await interaction.channel.send(embed=embed)

    async def _save_config_async(self):
        """Salva config in modo asincrono"""
        try:
            self.save_config()
        except Exception as e:
            print(f"Errore nel salvataggio config: {e}")

    def get_ticket_group(self):
        return self.ticket_group

async def setup(bot):
    await bot.add_cog(Tickets(bot))
