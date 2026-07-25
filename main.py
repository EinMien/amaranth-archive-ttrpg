import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import time

# ==========================================
# CONFIGURATION & DATABASE HELPERS
# ==========================================
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# Replace with the actual DM/Admin User IDs
ADMIN_USER_IDS = [int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]

def load_data(filename):
    filepath = f"data/{filename}.json"
    if not os.path.exists(filepath):
        os.makedirs("data", exist_ok=True)
        if filename == "groups":
            default_data = {"statuses": {}, "items": {}}
            with open(filepath, "w") as f:
                json.dump(default_data, f)
            return default_data
        else:
            with open(filepath, "w") as f:
                json.dump({}, f)
            return {}
    with open(filepath, "r") as f:
        data = json.load(f)
        if filename == "groups" and not data:
            return {"statuses": {}, "items": {}}
        return data

def save_data(filename, data):
    filepath = f"data/{filename}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

db = {
    "items": load_data("items"),
    "statuses": load_data("statuses"),
    "badges": load_data("badges"), # NEW BADGES DATABASE
    "players": load_data("players"),
    "groups": load_data("groups"),
    "shop": load_data("shop"),
    "wallet": load_data("wallet"),
    "metronomes": load_data("metronomes")
}

# --- Permission & Data Helpers ---

def grant_item(char_name, display_title, quantity, max_uses, preference="Neutral", starting_uses=None, guild_id=None):
    if char_name.startswith("Storage: "):
        party_name = char_name[9:]
        if guild_id and guild_id in db.get("wallet", {}) and party_name in db["wallet"][guild_id].get("parties", {}):
            inv = db["wallet"][guild_id]["parties"][party_name].setdefault("storage", {})
            limit = 50 
            if len(inv) + quantity > limit:
                return False, f"Storage limit exceeded (Max: {limit})"
            
            for _ in range(quantity):
                new_uid = generate_uid(display_title)
                inv[new_uid] = {
                    "name": display_title,
                    "uses": starting_uses if starting_uses is not None else max_uses,
                    "max_uses": max_uses,
                    "preference": preference
                }
            save_data("wallet", db["wallet"])
            return True, ""
        return False, "Party storage not found."

    for uid, pdata in db["players"].items():
        if "characters" in pdata and char_name in pdata["characters"]:
            inv = pdata["characters"][char_name].setdefault("inventory", {})
            stats = pdata["characters"][char_name].get("stats", {})
            limit = 20 if stats.get("dimensional_satchel", False) else 16
            if len(inv) + quantity > limit:
                return False, f"Inventory limit exceeded (Max: {limit})"
            
            for _ in range(quantity):
                new_uid = generate_uid(display_title)
                inv[new_uid] = {
                    "name": display_title,
                    "uses": starting_uses if starting_uses is not None else max_uses,
                    "max_uses": max_uses,
                    "preference": preference
                }
            save_data("players", db["players"])
            return True, ""
    return False, "Target character not found."


def get_active_name(interaction: discord.Interaction) -> str:
    player_key = f"{interaction.user.id}_{interaction.guild_id}"
    if player_key in db["players"] and db["players"][player_key].get("active"):
        return db["players"][player_key]["active"]
    return interaction.user.display_name

def get_allowed_targets(interaction: discord.Interaction) -> list[str]:
    player_key = f"{interaction.user.id}_{interaction.guild_id}"
    guild_id = str(interaction.guild_id) if interaction.guild_id else None
    
    my_chars = db["players"].get(player_key, {}).get("roster", [])
    
    if interaction.user.id in ADMIN_USER_IDS:
        scope = db.get("dms", {}).get(str(interaction.user.id), {}).get("target_scope", "global")
        if scope == "global":
            all_chars = []
            for pdata in db["players"].values():
                all_chars.extend(pdata.get("roster", []))
            
            if guild_id and guild_id in db.get("wallet", {}):
                for p_name in db["wallet"][guild_id].get("parties", {}).keys():
                    all_chars.append(f"Storage: {p_name}")
            return list(set(all_chars))
        elif scope == "own":
            return my_chars
        elif scope == "party" and guild_id:
            active = get_active_party(guild_id)
            if guild_id in db.get("wallet", {}) and active in db["wallet"][guild_id].get("parties", {}):
                return list(set(db["wallet"][guild_id]["parties"][active].get("members", []) + my_chars + [f"Storage: {active}"]))
            return my_chars
            
    allowed = list(my_chars)
    if guild_id and guild_id in db.get("wallet", {}):
        parties = db["wallet"][guild_id].get("parties", {})
        active_char = db["players"].get(player_key, {}).get("active")
        
        # Add members of the active character's party
        if active_char:
            for p_name, p_data in parties.items():
                if active_char in p_data.get("members", []):
                    allowed.extend(p_data.get("members", []))
                    allowed.append(f"Storage: {p_name}")
                    break
        
        # If active character isn't in a party, add members of any party they're in
        for c in my_chars:
            for p_name, p_data in parties.items():
                if c in p_data.get("members", []):
                    allowed.extend(p_data.get("members", []))
                    allowed.append(f"Storage: {p_name}")
                    
    return list(set(allowed))

def validate_target(interaction: discord.Interaction, target: str) -> bool:
    if not target: return True
    allowed = get_allowed_targets(interaction)
    return target in allowed

def can_edit(interaction: discord.Interaction, char_name: str) -> bool:
    if interaction.user.id in ADMIN_USER_IDS:
        return True
    return validate_target(interaction, char_name)

def get_char_data(char_name: str, guild_id: str) -> dict:
    for key, pdata in db["players"].items():
        if key.endswith(f"_{guild_id}"):
            if "characters" in pdata and char_name in pdata["characters"]:
                return pdata["characters"][char_name]
    return None

def generate_uid(item_name: str) -> str:
    # 32-bit FNV-1a hash - Extremely fast, low memory footprint
    data = f"{item_name}_{time.time()}_{random.random()}"
    hash_val = 0x811c9dc5
    for char in data:
        hash_val ^= ord(char)
        hash_val = (hash_val * 0x01000193) & 0xffffffff
    return hex(hash_val)[2:]

def get_item_base_data(item_name: str) -> tuple:
    for g_name, items in db["items"].items():
        for k, v in items.items():
            if k.lower() == item_name.lower() or v.get("title", k.title()).lower() == item_name.lower():
                return g_name, k, v
    for g_name, badges in db.get("badges", {}).items():
        for k, v in badges.items():
            if k.lower() == item_name.lower() or v.get("title", k.title()).lower() == item_name.lower():
                return g_name, k, v
    return None, None, None

def parse_uses(uses_str: str):
    try: return int(uses_str)
    except ValueError: return uses_str # Leaves "Infinite" as a string

# ==========================================
# BOT INITIALIZATION
# ==========================================
def add_chunked_field(embed: discord.Embed, name: str, value: str):
    if len(name) > 250:
        name = name[:247] + "..."
    # Rough estimate of current embed size
    current_size = len(embed.title or "") + len(embed.description or "")
    for field in embed.fields:
        current_size += len(field.name) + len(field.value)
        
    if len(value) <= 1024:
        if current_size + len(name) + len(value) > 5900:
            embed.add_field(name=name, value="*(Text truncated due to Discord limit)*", inline=False)
            return
        embed.add_field(name=name, value=value, inline=False)
        return
        
    text_remaining = value
    chunks = []
    while len(text_remaining) > 1024:
        split_idx = text_remaining.rfind('\n', 0, 1024)
        if split_idx == -1: split_idx = text_remaining.rfind(' ', 0, 1024)
        if split_idx == -1: split_idx = 1024
        chunks.append(text_remaining[:split_idx])
        text_remaining = text_remaining[split_idx:].lstrip()
        
    if text_remaining:
        chunks.append(text_remaining)
        
    for i, chunk in enumerate(chunks):
        title = name if i == 0 else f"â†³ {name} (Pt. {i+1})"
        if len(title) > 256:
            title = title[:253] + "..."
        if current_size + len(title) + len(chunk) > 5900:
            embed.add_field(name=title, value="*(Text truncated due to Discord limit)*", inline=False)
            break
        embed.add_field(name=title, value=chunk, inline=False)
        current_size += len(title) + len(chunk)

class TTRPGBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands synced globally!")

import logging
import traceback

# ==========================================
# EXCEPTION LOGGING
# ==========================================
logger = logging.getLogger('discord')
logger.setLevel(logging.ERROR)
handler = logging.FileHandler(filename='bot_errors.log', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


async def global_ui_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
    logger.error(f"UI Error on {item}:", exc_info=error)
    try:
        msg = "âŒ An internal UI error occurred. Admin has been notified."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except:
        pass

discord.ui.View.on_error = global_ui_error
discord.ui.Modal.on_error = global_ui_error

bot = TTRPGBot()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(f"Error in command '{interaction.command.name if interaction.command else 'Unknown'}':", exc_info=error)
    try:
        msg = "âŒ An internal error occurred. This has been logged for dev analysis."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to send error message to user:", exc_info=e)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# ==========================================
# AUTOCOMPLETE LOGIC
# ==========================================
async def status_group_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=g, value=g) for g in db["groups"]["statuses"].keys() if current.lower() in g.lower()][:25]

async def item_group_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=g, value=g) for g in db["groups"]["items"].keys() if current.lower() in g.lower()][:25]

async def status_name_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    group = interaction.namespace.group
    if not group or group not in db["statuses"]: return []
    choices = []
    for k, v in db["statuses"][group].items():
        if current.lower() in k.lower() or current.lower() in v.get("title", "").lower() or any(current.lower() in a for a in v.get("aliases", [])):
            choices.append(app_commands.Choice(name=v.get("title", k.title())[:100], value=k))
    return choices[:25]

async def item_name_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    group = interaction.namespace.group
    if not group or group not in db["items"]: return []
    choices = []
    for k, v in db["items"][group].items():
        if current.lower() in k.lower() or current.lower() in v.get("title", "").lower() or any(current.lower() in a for a in v.get("aliases", [])):
            choices.append(app_commands.Choice(name=v.get("title", k.title())[:100], value=k))
    return choices[:25]

async def item_variant_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    group = interaction.namespace.group
    name = interaction.namespace.name
    if not group or not name or group not in db["items"] or name not in db["items"][group]: return []
    variants = db["items"][group][name].get("variants", {})
    return [app_commands.Choice(name=v, value=v) for v in variants.keys() if current.lower() in v.lower()][:25]

async def status_variant_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    group = interaction.namespace.group
    name = interaction.namespace.name
    if not group or not name or group not in db["statuses"] or name not in db["statuses"][group]: return []
    variants = db["statuses"][group][name].get("variants", {})
    return [app_commands.Choice(name=v, value=v) for v in variants.keys() if current.lower() in v.lower()][:25]

async def statustype_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name="Any Random", value="random")]
    for g in db["groups"]["statuses"].keys():
        if current.lower() in g.lower():
            choices.append(app_commands.Choice(name=g, value=g))
    return choices[:25]
    
async def itemtype_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name="Any Non-Special", value="any non-special")]
    for g in db["groups"]["items"].keys():
        if current.lower() in g.lower():
            choices.append(app_commands.Choice(name=g, value=g))
    return choices[:25]

async def character_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    player_key = f"{interaction.user.id}_{interaction.guild_id}"
    if player_key not in db["players"]: return []
    return [app_commands.Choice(name=c, value=c) for c in db["players"][player_key].get("roster", []) if current.lower() in c.lower()][:25]

async def target_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    allowed = get_allowed_targets(interaction)
    return [app_commands.Choice(name=c, value=c) for c in allowed if current.lower() in c.lower()][:25]

async def character_target_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    allowed = get_allowed_targets(interaction)
    return [app_commands.Choice(name=c, value=c) for c in allowed if current.lower() in c.lower() and not c.startswith("Storage: ")][:25]

async def magic_name_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    char_name = interaction.namespace.target or get_active_name(interaction)
    char_data = get_char_data(char_name, str(interaction.guild_id))
    if not char_data or "magic" not in char_data: return []
    choices = []
    for m in char_data["magic"].keys():
        if current.lower() in m.lower():
            choices.append(app_commands.Choice(name=m[:100], value=m[:100]))
    return choices[:25]

async def global_item_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = []
    for g_data in db["items"].values():
        for k, v in g_data.items():
            if current.lower() in k.lower() or current.lower() in v.get("title", "").lower():
                choices.append(app_commands.Choice(name=v.get("title", k.title())[:100], value=k))
                if len(choices) >= 25:
                    return choices
    return choices

async def metronome_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    matches = []
    for name in db.get("metronomes", {}).keys():
        if current.lower() in name.lower():
            matches.append(name)
    return [app_commands.Choice(name=m, value=m) for m in matches][:25]

async def char_item_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    char_name = interaction.namespace.target or get_active_name(interaction)
    char_data = get_char_data(char_name, str(interaction.guild_id))
    if not char_data or "inventory" not in char_data: return []
    
    unique_names = set()
    for i_uid, item_data in char_data["inventory"].items():
        unique_names.add(item_data.get("name", i_uid))
        
    return [app_commands.Choice(name=n, value=n) for n in unique_names if current.lower() in n.lower()][:25]

async def badge_group_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=g, value=g) for g in db["groups"].get("badges", {}).keys() if current.lower() in g.lower()][:25]

async def badge_name_auto(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    group = interaction.namespace.group
    if not group or group not in db["badges"]: return []
    choices = []
    for k, v in db["badges"][group].items():
        if current.lower() in k.lower() or current.lower() in v.get("title", "").lower() or any(current.lower() in a for a in v.get("aliases", [])):
            choices.append(app_commands.Choice(name=v.get("title", k.title())[:100], value=k))
    return choices[:25]

# ==========================================
# INTERACTIVE VIEWS
# ==========================================
class VariantView(discord.ui.View):
    def __init__(self, category: str, group: str, base_title: str, base_data: dict, embed_color: discord.Color):
        super().__init__(timeout=None)
        self.category = category
        self.group = group
        self.base_title = base_title
        self.base_data = base_data
        self.embed_color = embed_color
        self.variants = base_data.get("variants", {})
        
        base_btn = discord.ui.Button(label="Base Version", style=discord.ButtonStyle.primary)
        base_btn.callback = self.make_callback(self.base_title, self.base_data)
        self.add_item(base_btn)
        
        for variant_name, variant_data in self.variants.items():
            btn = discord.ui.Button(label=variant_name, style=discord.ButtonStyle.primary)
            btn.callback = self.make_callback(f"{self.base_title} ({variant_name})", variant_data)
            self.add_item(btn)

    def make_callback(self, display_title, data):
        async def button_callback(interaction: discord.Interaction):
            char_name = get_active_name(interaction)
            effect = data.get("effect", "No effect provided.")
            flavor = data.get("description", data.get("text", "")).replace("_", char_name)
            
            body = f"**Group:** {self.group}\n"
            
            if self.category == "items":
                uses = data.get("uses", self.base_data.get("uses", "1"))
                body += f"**Uses:** {uses}\n"
                
            body += f"**Effect:**\n{effect}"
            
            if flavor:
                label = "Description" if "description" in data else "Text"
                body += f"\n\n*{label}: \"{flavor}\"*"
                
            embed = discord.Embed(title=display_title, description=body, color=self.embed_color)
            await interaction.response.edit_message(embed=embed)
        return button_callback

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hi!", style=discord.ButtonStyle.primary)
    async def btn_hi(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"Hai {interaction.user.mention} :3")

    @discord.ui.button(label="Goodbye", style=discord.ButtonStyle.primary)
    async def btn_bye(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"Aww... Goodbye {interaction.user.mention}!")

class MovesheetView(discord.ui.View):
    def __init__(self, char_name: str, char_data: dict, guild_id: str = None):
        super().__init__(timeout=None)
        self.char_name = char_name
        self.char_data = char_data
        self.guild_id = guild_id

    def build_stats_embed(self):
        stats = self.char_data.get("stats", {})
        equips = self.char_data.get("equips", {})
        ability = self.char_data.get("ability", {})
        
        embed = discord.Embed(title=f"ðŸ“Š {self.char_name}'s Stats", color=discord.Color.blurple())
        embed.add_field(name="HP", value=f"{stats.get('current_hp', 0)} / {stats.get('max_hp', 0)}", inline=False)
        
        fight_str = f"**HIT:** {stats.get('fight_hit', '+0')} | **Damage:** {stats.get('fight_damage', '+0')} | **DODGE:** {stats.get('dodge', '+0')}"
        fight_effect = stats.get('fight_effect', 'None')
        if fight_effect and fight_effect.lower() != "none":
            fight_str += f"\n**Effect:** {fight_effect}"
            
        embed.add_field(name="FIGHT and DODGE", value=fight_str, inline=False)
        
        max_hearts = 3
        if self.guild_id and self.guild_id in db.get("wallet", {}):
            parties = db["wallet"][self.guild_id].get("parties", {})
            for party_name, party_data in parties.items():
                if self.char_name in party_data.get("members", []):
                    max_hearts = party_data.get("max_hearts", 3)
                    break

        equip_str = (
            f"**Weapon:** {equips.get('weapon', 'None')}\n"
            f"**Armor:** {equips.get('armor', 'None')}\n"
            f"**Badge 1:** {equips.get('badge_1', 'N/A')}\n"
            f"**Badge 2:** {equips.get('badge_2', 'N/A')}\n"
            f"**Badge 3:** {equips.get('badge_3', 'Need Extra Pin')}\n"
            f"**Crystal Hearts:** {stats.get('crystal_hearts', 0)}/{max_hearts}\n"
            f"**Dimensional Satchel:** {stats.get('dimensional_satchel', False)}"
        )
        embed.add_field(name="Equips", value=equip_str, inline=False)
        
        add_chunked_field(embed, f"ABILITY: {ability.get('name', 'None')}", ability.get('effect', 'None'))
        
        chocs = f"White: {stats.get('choc_white', 0)} | Milk: {stats.get('choc_milk', 0)} | Dark: {stats.get('choc_dark', 0)}"
        embed.set_footer(text=f"Chocolate Ratings: {chocs}")
        return embed

    def build_magic_embed(self):
        embed = discord.Embed(title=f"âœ¨ {self.char_name}'s Magic", color=discord.Color.purple())
        magic_dict = self.char_data.get("magic", {})
        
        if not magic_dict:
            embed.description = "*No MAGIC learned yet.*"
        else:
            for m_name, m_data in magic_dict.items():
                is_ult = m_data.get('is_ultimate', False)
                header = f"ðŸŒŸ {m_name} (Ultimate)" if is_ult else f"{m_name}"
                
                body = (
                    f"**HIT:** {m_data.get('hit', 'N/A')} | "
                    f"**Damage:** {m_data.get('damage', 'N/A')}\n"
                    f"**Effect:** {m_data.get('effect', 'None')}\n"
                    f"**Cooldown:** {m_data.get('cooldown', '0')}"
                )
                add_chunked_field(embed, header, body)
                        
        return embed

    def build_inventory_embed(self):
        embed = discord.Embed(title=f"ðŸŽ’ {self.char_name}'s Inventory", color=discord.Color.green())
        inv = self.char_data.get("inventory", {})
        if not inv:
            embed.description = "*Inventory is empty.*"
            return embed
            
        grouped = {}
        for uid, data in inv.items():
            name = data.get("name", uid) 
            if name not in grouped: grouped[name] = []
            grouped[name].append(data)
            
        items_text = ""
        for name in sorted(grouped.keys()):
            instances = grouped[name]
            pref = instances[0].get("preference", "Neutral")
            
            if "quantity" in instances[0]:
                count = instances[0]["quantity"]
                uses_list = ["Illegal Item - Re-add to track uses"]
            else:
                count = len(instances)
                uses_list = []
                for inst in instances:
                    u = inst.get("uses", 1)
                    mu = inst.get("max_uses", 1)
                    uses_list.append(f"{u}/{mu}" if isinstance(u, int) else str(u))
            
            items_text += f"â€¢ **{name}** x{count} *(Pref: {pref})* - Uses: [{', '.join(uses_list)}]\n"
            
        embed.description = items_text
        return embed

    def build_preferences_embed(self):
        embed = discord.Embed(title=f"â¤ï¸ {self.char_name}'s Item Preferences", color=discord.Color.teal())
        prefs = self.char_data.get("preferences", {})
        
        if not prefs:
            embed.description = "*All items are currently at Neutral preference.*"
            return embed
            
        tiers = {"Obsessed": [], "Well-Liked": [], "Disliked": [], "Allergic": []}
        for item, pref in prefs.items():
            if pref in tiers:
                base = get_item_base_data(item)
                if base and base[2]:
                    title = base[2].get("title", item.title())
                else:
                    title = item.title()
                tiers[pref].append(title)
                
        has_any = False
        for tier, items in tiers.items():
            if items:
                has_any = True
                items.sort()
                embed.add_field(name=tier, value=", ".join(items), inline=False)
                
        if not has_any:
            embed.description = "*All items are currently at Neutral preference.*"
            
        return embed

    @discord.ui.button(label="Base Stats", style=discord.ButtonStyle.primary, custom_id="ms_stats")
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.build_stats_embed())

    @discord.ui.button(label="Magic", style=discord.ButtonStyle.primary, custom_id="ms_magic")
    async def btn_magic(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.build_magic_embed())

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.primary, custom_id="ms_inv")
    async def btn_inv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.build_inventory_embed())


    def build_trap_embed(self) -> discord.Embed:
        ostats = self.char_data.get("other_stats", {})
        caut = ostats.get("cautiousness", "0")
        dex = ostats.get("dexterity", "0")
        timer = ostats.get("timer", "+0")
        t_name = ostats.get("trap_name", "None")
        t_eff = ostats.get("trap_effect", "None")
        r_name = ostats.get("race_name", "None")
        r_eff = ostats.get("race_effect", "None")
        
        embed = discord.Embed(title=f"âš™ï¸ Trap & Race Stats: {self.char_name}", color=discord.Color.dark_grey())
        embed.add_field(name="Cautiousness", value=caut, inline=True)
        embed.add_field(name="Dexterity", value=dex, inline=True)
        embed.add_field(name="Timer", value=timer, inline=True)
        
        if t_name != "None":
            add_chunked_field(embed, f"ðŸª¤ Trap Quirk: {t_name}", t_eff)
        else:
            embed.add_field(name="ðŸª¤ Trap Quirk", value="None", inline=False)
            
        if r_name != "None":
            add_chunked_field(embed, f"ðŸŽï¸ Race Whim: {r_name}", r_eff)
        else:
            embed.add_field(name="ðŸŽï¸ Race Whim", value="None", inline=False)
            
        return embed

    @discord.ui.button(label="Trap & Race", style=discord.ButtonStyle.primary, custom_id="ms_trap")
    async def btn_trap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.build_trap_embed())

    @discord.ui.button(label="Preferences", style=discord.ButtonStyle.primary, custom_id="ms_prefs")
    async def btn_prefs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.build_preferences_embed())

# ==========================================
# ITEM INSTANCE VIEWS
# ==========================================
async def process_item_use(interaction: discord.Interaction, target_name: str, author_name: str, owner_id: str, uid: str, action: str = "use", use_times: int = 1, guild_id: str = None):
    if author_name.startswith("Storage: "):
        party_name = author_name[9:]
        inv = db["wallet"][guild_id]["parties"][party_name]["storage"]
    else:
        inv = db["players"][owner_id]["characters"][author_name]["inventory"]
        
    if uid not in inv:
        return await interaction.response.send_message("âŒ Item instance not found.", ephemeral=True)
        
    item_inst = inv[uid]
    item_name = item_inst.get("name", uid) 
    
    if action == "take":
        if "quantity" in item_inst: 
            item_inst["quantity"] -= 1
            if item_inst["quantity"] <= 0: del inv[uid]
        else:
            del inv[uid]
            
        if author_name.startswith("Storage: "):
            save_data("wallet", db["wallet"])
        else:
            save_data("players", db["players"])
        return await interaction.response.send_message(f"ðŸ—‘ï¸ Removed one instance of **{item_name}** from **{author_name}**.", ephemeral=True)
    
    times_text = f" {use_times} times" if use_times > 1 else ""
    
    if "quantity" in item_inst:
        used_text = f"**{author_name}** used **{item_name}**{times_text} on **{target_name}**! *(Old format)*"
    else:
        uses = item_inst.get("uses", 1)
        if isinstance(uses, int):
            if uses < use_times:
                return await interaction.response.send_message(f"âŒ This instance only has {uses} uses left.", ephemeral=True)
            item_inst["uses"] -= use_times
            if item_inst["uses"] <= 0:
                del inv[uid]
                used_text = f"**{author_name}** used **{item_name}**{times_text} on **{target_name}**, consuming it!"
            else:
                used_text = f"**{author_name}** used **{item_name}**{times_text} on **{target_name}**! ({item_inst['uses']}/{item_inst['max_uses']} uses left)."
        else:
            used_text = f"**{author_name}** used **{item_name}**{times_text} on **{target_name}**! (Infinite uses)."
        
    if author_name.startswith("Storage: "):
        save_data("wallet", db["wallet"])
    else:
        save_data("players", db["players"])
    
    group, key, base_data = get_item_base_data(item_name)
    effect = base_data.get("effect", "No mechanical effect provided.") if base_data else "Unknown."
    flavor = base_data.get("description", "").replace("_", target_name) if base_data else ""
    pref = item_inst.get("preference", "Neutral")
    
    desc = f"{used_text}\n\n**Preference:** {pref}\n**Effect:**\n{effect}"
    if flavor:
        desc += f"\n\n*\"{flavor}\"*"
        
    embed = discord.Embed(title=f"ðŸŽ’ {author_name} used {item_name}!", description=desc, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

class DashboardSelect(discord.ui.Select):
    def __init__(self, action: str, placeholder: str, options: list, row: int):
        super().__init__(placeholder=placeholder, min_values=1, max_values=len(options), options=options, row=row, custom_id=f"dash_sel_{action}_{row}")
        self.action_type = action

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        await view.process_transfer(interaction, self.action_type, self.values)

class DashboardButton(discord.ui.Button):
    def __init__(self, label: str, action: str, row: int, disabled: bool):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row, disabled=disabled, custom_id=f"dash_btn_{action}_{row}")
        self.action_type = action
        
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        await view.process_pagination(interaction, self.action_type)

class StorageDashboardView(discord.ui.View):
    def __init__(self, char_name: str, guild_id: str, target_party: str, inv_page: int = 0, sto_page: int = 0):
        super().__init__(timeout=None)
        self.char_name = char_name
        self.guild_id = guild_id
        self.target_party = target_party
        self.inv_page = inv_page
        self.sto_page = sto_page
        self.refresh_state()
        
    def get_char_pdata(self):
        for key, pdata in db["players"].items():
            if key.endswith(f"_{self.guild_id}"):
                if "characters" in pdata and self.char_name in pdata["characters"]:
                    return key, pdata
        return None, None
        
    def build_embed(self) -> discord.Embed:
        uid, pdata = self.get_char_pdata()
        char_inv = pdata["characters"][self.char_name].get("inventory", {}) if pdata else {}
        stats = pdata["characters"][self.char_name].get("stats", {}) if pdata else {}
        limit = 20 if stats.get("dimensional_satchel", False) else 16
        
        wallet = db["wallet"][self.guild_id]["parties"][self.target_party]
        storage = wallet.get("storage", {})
        
        embed = discord.Embed(title=f"ðŸ“¦ Storage Dashboard: {self.target_party}", description=f"Transferring items with **{self.char_name}**", color=discord.Color.dark_grey())
        embed.add_field(name="Inventory", value=f"{len(char_inv)} / {limit} items", inline=True)
        embed.add_field(name="Storage", value=f"{len(storage)} items", inline=True)
        return embed

    def refresh_state(self):
        self.clear_items()
        uid, pdata = self.get_char_pdata()
        if not pdata: return
        
        wallet = db["wallet"][self.guild_id]["parties"][self.target_party]
        if "storage" not in wallet: wallet["storage"] = {}
        storage = wallet["storage"]
        
        char_inv = pdata["characters"][self.char_name].setdefault("inventory", {})
        
        self.all_inv = list(char_inv.items())
        self.all_inv.sort(key=lambda x: x[1].get("name", x[0]))
        self.all_sto = list(storage.items())
        self.all_sto.sort(key=lambda x: x[1].get("name", x[0]))
        
        self.inv_total = max(1, (len(self.all_inv) + 24) // 25)
        self.sto_total = max(1, (len(self.all_sto) + 24) // 25)
        
        self.inv_page = min(self.inv_page, self.inv_total - 1)
        self.sto_page = min(self.sto_page, self.sto_total - 1)
        
        inv_chunk = self.all_inv[self.inv_page * 25 : (self.inv_page + 1) * 25]
        sto_chunk = self.all_sto[self.sto_page * 25 : (self.sto_page + 1) * 25]
        
        def build_options(chunk):
            ops = []
            for item_uid, data in chunk:
                u_text = f"{data['uses']}/{data.get('max_uses', data['uses'])} uses" if isinstance(data.get('uses'), int) else str(data.get('uses', '1'))
                ops.append(discord.SelectOption(label=f"{data.get('name', item_uid)[:50]} ({u_text})", value=item_uid))
            return ops
            
        inv_options = build_options(inv_chunk)
        sto_options = build_options(sto_chunk)
        
        if inv_options:
            self.add_item(DashboardSelect("deposit", "Select items to deposit...", inv_options, 0))
        else:
            self.add_item(discord.ui.Select(placeholder="Inventory is empty.", options=[discord.SelectOption(label="Empty", value="empty")], disabled=True, row=0, custom_id="empty_inv"))
            
        if self.inv_total > 1:
            self.add_item(DashboardButton("â—€ Prev Inv", "inv_prev", 1, self.inv_page == 0))
            self.add_item(DashboardButton("Next Inv â–¶", "inv_next", 1, self.inv_page == self.inv_total - 1))
            
        if sto_options:
            self.add_item(DashboardSelect("withdraw", "Select items to withdraw...", sto_options, 2))
        else:
            self.add_item(discord.ui.Select(placeholder="Storage is empty.", options=[discord.SelectOption(label="Empty", value="empty")], disabled=True, row=2, custom_id="empty_sto"))
            
        if self.sto_total > 1:
            self.add_item(DashboardButton("â—€ Prev Storage", "sto_prev", 3, self.sto_page == 0))
            self.add_item(DashboardButton("Next Storage â–¶", "sto_next", 3, self.sto_page == self.sto_total - 1))

    async def process_pagination(self, interaction: discord.Interaction, action: str):
        if action == "inv_prev": self.inv_page -= 1
        elif action == "inv_next": self.inv_page += 1
        elif action == "sto_prev": self.sto_page -= 1
        elif action == "sto_next": self.sto_page += 1
        
        self.refresh_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def process_transfer(self, interaction: discord.Interaction, action: str, uids: list):
        uid, pdata = self.get_char_pdata()
        char_inv = pdata["characters"][self.char_name]["inventory"]
        wallet = db["wallet"][self.guild_id]["parties"][self.target_party]
        storage = wallet["storage"]
        
        if action == "deposit":
            for u in uids:
                if u in char_inv:
                    storage[u] = char_inv[u]
                    del char_inv[u]
            msg = f"ðŸ“¥ Deposited {len(uids)} items."
        else:
            stats = pdata["characters"][self.char_name].get("stats", {})
            limit = 20 if stats.get("dimensional_satchel", False) else 16
            if len(char_inv) + len(uids) > limit:
                return await interaction.response.send_message(f"âŒ **{self.char_name}** does not have enough inventory space (Limit: {limit}).", ephemeral=True)
                
            for u in uids:
                if u in storage:
                    char_inv[u] = storage[u]
                    del storage[u]
            msg = f"ðŸ“¤ Withdrew {len(uids)} items."
            
        save_data("wallet", db["wallet"])
        save_data("players", db["players"])
        
        self.refresh_state()
        await interaction.response.edit_message(content=msg, embed=self.build_embed(), view=self)

class ItemInstanceSelect(discord.ui.Select):
    def __init__(self, target_name: str, author_name: str, owner_id: str, item_name: str, instances: dict, action: str, use_times: int = 1, guild_id: str = None):
        self.target_name = target_name
        self.author_name = author_name
        self.owner_id = owner_id
        self.item_name = item_name
        self.action = action
        self.use_times = use_times
        self.guild_id = guild_id
        options = []
        for uid, data in instances.items():
            if "quantity" in data:
                u_text = f"Old Format (Qty: {data['quantity']})"
            else:
                u_text = f"{data['uses']}/{data['max_uses']} uses" if isinstance(data['uses'], int) else data['uses']

            options.append(discord.SelectOption(label=f"{item_name[:50]} ({u_text})", description=f"ID: {uid[:50]}", value=uid))

        super().__init__(placeholder="Multiple found. Choose which instance:", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        uid = self.values[0]
        await process_item_use(interaction, self.target_name, self.author_name, self.owner_id, uid, self.action, self.use_times, self.guild_id)

class ItemInstanceView(discord.ui.View):
    def __init__(self, target_name: str, author_name: str, owner_id: str, item_name: str, instances: dict, action: str, use_times: int = 1, guild_id: str = None):
        super().__init__()
        self.add_item(ItemInstanceSelect(target_name, author_name, owner_id, item_name, instances, action, use_times, guild_id))

# ==========================================
# PLAYER CHARACTER & SHEET COMMANDS
# ==========================================
@bot.tree.command(name="addchar", description="Register a new character to your roster")
async def cmd_addchar(interaction: discord.Interaction, name: str):
    uid = f"{interaction.user.id}_{interaction.guild_id}"
    if uid not in db["players"]:
        db["players"][uid] = {"active": name, "roster": [], "characters": {}}
    
    if "characters" not in db["players"][uid]:
        db["players"][uid]["characters"] = {}
        
    if name not in db["players"][uid]["roster"]:
        db["players"][uid]["roster"].append(name)
        db["players"][uid]["characters"][name] = {
            "stats": {
                "max_hp": 100, "current_hp": 100, "fight_hit": "+0", 
                "fight_damage": "+0", "dodge": "+0", "fight_effect": "None",
                "choc_white": 0, "choc_milk": 0, "choc_dark": 0
            },
            "equips": {
                "weapon": "None", 
                "armor": "None", 
                "badge_1": "N/A", 
                "badge_2": "N/A", 
                "badge_3": "Need Extra Pin"
            },
            "ability": {"name": "None", "effect": "None"},
            "magic": {},
            "inventory": {}
        }
        
    db["players"][uid]["active"] = name
    save_data("players", db["players"])
    view = CharacterBuilderView(name, uid)
    await interaction.response.send_message(f"âœ… Character **{name}** registered! Use the dashboard below to set them up:", view=view, ephemeral=True)

@bot.tree.command(name="setchar", description="Switch your active character")
@app_commands.autocomplete(name=character_auto)
async def cmd_setchar(interaction: discord.Interaction, name: str):
    uid = f"{interaction.user.id}_{interaction.guild_id}"
    if uid in db["players"] and name in db["players"][uid].get("roster", []):
        db["players"][uid]["active"] = name
        save_data("players", db["players"])
        await interaction.response.send_message(f"ðŸ”„ Active character set to **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("âŒ Character not found. Use `/addchar` first.", ephemeral=True)

@bot.tree.command(name="removechar", description="Remove a character from your roster")
@app_commands.autocomplete(name=character_auto)
async def cmd_removechar(interaction: discord.Interaction, name: str):
    uid = f"{interaction.user.id}_{interaction.guild_id}"
    if uid in db["players"] and name in db["players"][uid].get("roster", []):
        db["players"][uid]["roster"].remove(name)
        if db["players"][uid]["active"] == name:
            db["players"][uid]["active"] = None
        if name in db["players"][uid].get("characters", {}):
            del db["players"][uid]["characters"][name]
        save_data("players", db["players"])
        await interaction.response.send_message(f"ðŸ—‘ï¸ Character **{name}** removed.", ephemeral=True)
    else:
        await interaction.response.send_message("âŒ Character not found.", ephemeral=True)

@bot.tree.command(name="movesheet", description="View a character's stats, magic, and inventory")
@app_commands.autocomplete(target=character_target_auto)
@app_commands.describe(target="Leave blank to view your active character")
async def cmd_movesheet(interaction: discord.Interaction, target: str = None):
    if target and target.startswith("Storage: "):
        return await interaction.response.send_message("âŒ Cannot view movesheet for a party storage.", ephemeral=True)
    if target and not validate_target(interaction, target):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)
    char_name = target if target else get_active_name(interaction)
    char_data = get_char_data(char_name, str(interaction.guild_id))
    
    if not char_data:
        return await interaction.response.send_message(f"âŒ Could not find data for **{char_name}**.", ephemeral=True)
        
    view = MovesheetView(char_name, char_data, str(interaction.guild_id))
    await interaction.response.send_message(embed=view.build_stats_embed(), view=view)

# --- Stat Setup Modals & Commands ---
class EditStatsModal(discord.ui.Modal, title="Edit Combat Stats"):
    hp_input = discord.ui.TextInput(label="Max HP (Current resets to this)", style=discord.TextStyle.short)
    hit_input = discord.ui.TextInput(label="FIGHT HIT Modifier (e.g. +5)", style=discord.TextStyle.short)
    dmg_input = discord.ui.TextInput(label="FIGHT Damage Modifier (e.g. +2)", style=discord.TextStyle.short)
    dodge_input = discord.ui.TextInput(label="DODGE Modifier (e.g. +3)", style=discord.TextStyle.short)
    effect_input = discord.ui.TextInput(label="FIGHT Effect (Optional)", style=discord.TextStyle.paragraph, max_length=4000, required=False)

    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        stats = db["players"][owner_id]["characters"][char_name]["stats"]
        self.hp_input.default = str(stats.get("max_hp", 100))
        self.hit_input.default = stats.get("fight_hit", "+0")
        self.dmg_input.default = stats.get("fight_damage", "+0")
        self.dodge_input.default = stats.get("dodge", "+0")
        self.effect_input.default = stats.get("fight_effect", "")

    async def on_submit(self, interaction: discord.Interaction):
        stats = db["players"][self.owner_id]["characters"][self.char_name]["stats"]
        try:
            stats["max_hp"] = int(self.hp_input.value)
            stats["current_hp"] = int(self.hp_input.value)
        except ValueError: pass
        stats["fight_hit"] = self.hit_input.value
        stats["fight_damage"] = self.dmg_input.value
        stats["dodge"] = self.dodge_input.value
        stats["fight_effect"] = self.effect_input.value or "None"
        
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Combat stats updated for **{self.char_name}**!", ephemeral=True)

class EditAbilityModal(discord.ui.Modal, title="Edit Unique ABILITY"):
    name_input = discord.ui.TextInput(label="Ability Name", style=discord.TextStyle.short)
    effect_input = discord.ui.TextInput(label="Ability Effect", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        ability = db["players"][owner_id]["characters"][char_name]["ability"]
        self.name_input.default = ability.get("name", "")
        self.effect_input.default = ability.get("effect", "")

    async def on_submit(self, interaction: discord.Interaction):
        ability = db["players"][self.owner_id]["characters"][self.char_name]["ability"]
        ability["name"] = self.name_input.value
        ability["effect"] = self.effect_input.value
        
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Ability updated for **{self.char_name}**!", ephemeral=True)



class EditEquipsModal(discord.ui.Modal, title="Edit Equipment & Badges"):
    wep_input = discord.ui.TextInput(label="Weapon", style=discord.TextStyle.short, required=False)
    arm_input = discord.ui.TextInput(label="Armor", style=discord.TextStyle.short, required=False)
    b1_input = discord.ui.TextInput(label="Badge 1", style=discord.TextStyle.short, required=False)
    b2_input = discord.ui.TextInput(label="Badge 2", style=discord.TextStyle.short, required=False)
    b3_input = discord.ui.TextInput(label="Badge 3 (Extra Pin)", style=discord.TextStyle.short, required=False)

    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        equips = db["players"][owner_id]["characters"][char_name].get("equips", {})
        
        self.wep_input.default = equips.get("weapon", "None")
        self.arm_input.default = equips.get("armor", "None")
        self.b1_input.default = equips.get("badge_1", "N/A")
        self.b2_input.default = equips.get("badge_2", "N/A")
        self.b3_input.default = equips.get("badge_3", "Need Extra Pin")

    async def on_submit(self, interaction: discord.Interaction):
        if "equips" not in db["players"][self.owner_id]["characters"][self.char_name]:
            db["players"][self.owner_id]["characters"][self.char_name]["equips"] = {}
            
        equips = db["players"][self.owner_id]["characters"][self.char_name]["equips"]
        
        equips["weapon"] = self.wep_input.value or "None"
        equips["armor"] = self.arm_input.value or "None"
        equips["badge_1"] = self.b1_input.value or "N/A"
        equips["badge_2"] = self.b2_input.value or "N/A"
        equips["badge_3"] = self.b3_input.value or "Need Extra Pin"
        
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Equipment updated for **{self.char_name}**!", ephemeral=True)


class EditChocsModal(discord.ui.Modal, title="Chocolate Ratings"):
    white = discord.ui.TextInput(label="White Chocolate", style=discord.TextStyle.short, default="0")
    milk = discord.ui.TextInput(label="Milk Chocolate", style=discord.TextStyle.short, default="0")
    dark = discord.ui.TextInput(label="Dark Chocolate", style=discord.TextStyle.short, default="0")
    
    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        stats = db["players"][owner_id]["characters"][char_name].get("stats", {})
        self.white.default = str(stats.get("choc_white", 0))
        self.milk.default = str(stats.get("choc_milk", 0))
        self.dark.default = str(stats.get("choc_dark", 0))
        
    async def on_submit(self, interaction: discord.Interaction):
        stats = db["players"][self.owner_id]["characters"][self.char_name].setdefault("stats", {})
        try: stats["choc_white"] = int(self.white.value)
        except: pass
        try: stats["choc_milk"] = int(self.milk.value)
        except: pass
        try: stats["choc_dark"] = int(self.dark.value)
        except: pass
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Chocolate ratings updated for **{self.char_name}**!", ephemeral=True)

class EditTrapStatsModal(discord.ui.Modal, title="Trap & Race Stats"):
    caut = discord.ui.TextInput(label="Cautiousness", style=discord.TextStyle.short, default="0")
    dex = discord.ui.TextInput(label="Dexterity", style=discord.TextStyle.short, default="0")
    timer = discord.ui.TextInput(label="Timer", style=discord.TextStyle.short, default="+0")
    
    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        ostats = db["players"][owner_id]["characters"][char_name].setdefault("other_stats", {})
        self.caut.default = ostats.get("cautiousness", "0")
        self.dex.default = ostats.get("dexterity", "0")
        self.timer.default = ostats.get("timer", "+0")
        
    async def on_submit(self, interaction: discord.Interaction):
        ostats = db["players"][self.owner_id]["characters"][self.char_name]["other_stats"]
        ostats["cautiousness"] = self.caut.value or "0"
        ostats["dexterity"] = self.dex.value or "0"
        ostats["timer"] = self.timer.value or "+0"
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Trap & Race stats updated for **{self.char_name}**!", ephemeral=True)

class EditQuirksModal(discord.ui.Modal, title="Quirks & Whims"):
    t_name = discord.ui.TextInput(label="Trap Quirk Name", style=discord.TextStyle.short, default="None", required=False)
    t_eff = discord.ui.TextInput(label="Trap Quirk Effect", style=discord.TextStyle.paragraph, max_length=4000, default="None", required=False)
    r_name = discord.ui.TextInput(label="Race Whim Name", style=discord.TextStyle.short, default="None", required=False)
    r_eff = discord.ui.TextInput(label="Race Whim Effect", style=discord.TextStyle.paragraph, max_length=4000, default="None", required=False)
    
    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        ostats = db["players"][owner_id]["characters"][char_name].setdefault("other_stats", {})
        self.t_name.default = ostats.get("trap_name", "None")
        self.t_eff.default = ostats.get("trap_effect", "None")
        self.r_name.default = ostats.get("race_name", "None")
        self.r_eff.default = ostats.get("race_effect", "None")
        
    async def on_submit(self, interaction: discord.Interaction):
        ostats = db["players"][self.owner_id]["characters"][self.char_name]["other_stats"]
        ostats["trap_name"] = self.t_name.value or "None"
        ostats["trap_effect"] = self.t_eff.value or "None"
        ostats["race_name"] = self.r_name.value or "None"
        ostats["race_effect"] = self.r_eff.value or "None"
        save_data("players", db["players"])
        await interaction.response.send_message(f"âœ… Quirks & Whims updated for **{self.char_name}**!", ephemeral=True)

class EditMagicModal(discord.ui.Modal, title="Add / Edit Magic"):
    m_name = discord.ui.TextInput(label="Magic Name", style=discord.TextStyle.short)
    m_ult = discord.ui.TextInput(label="Is Ultimate? (Y/N)", style=discord.TextStyle.short, default="N")
    m_combat = discord.ui.TextInput(label="Hit / Damage (e.g. +5 / +2)", style=discord.TextStyle.short, default="N/A / N/A")
    m_cd = discord.ui.TextInput(label="Cooldown", style=discord.TextStyle.short, default="0")
    m_effect = discord.ui.TextInput(label="Effect", style=discord.TextStyle.paragraph, max_length=4000, default="None")
    
    def __init__(self, char_name: str, owner_id: str):
        super().__init__()
        self.char_name = char_name
        self.owner_id = owner_id
        
    async def on_submit(self, interaction: discord.Interaction):
        m_name = self.m_name.value.strip()
        is_ult = self.m_ult.value.strip().lower() in ["y", "yes", "true", "1"]
        combat_parts = self.m_combat.value.split("/")
        hit = combat_parts[0].strip() if len(combat_parts) > 0 else "N/A"
        dmg = combat_parts[1].strip() if len(combat_parts) > 1 else "N/A"
        cd = self.m_cd.value.strip() or "0"
        effect = self.m_effect.value.strip() or "None"
        
        if "magic" not in db["players"][self.owner_id]["characters"][self.char_name]:
            db["players"][self.owner_id]["characters"][self.char_name]["magic"] = {}
            
        db["players"][self.owner_id]["characters"][self.char_name]["magic"][m_name] = {
            "is_ultimate": is_ult,
            "hit": hit,
            "damage": dmg,
            "cooldown": cd,
            "effect": effect
        }
        
        save_data("players", db["players"])
        view = CharacterBuilderView(self.char_name, self.owner_id)
        try:
            await interaction.response.edit_message(content=f"âœ… MAGIC **{m_name}** saved! Returning to Dashboard:", view=view, embed=None)
        except:
            await interaction.response.send_message(f"âœ… MAGIC **{m_name}** saved!", ephemeral=True)

class CharacterBuilderView(discord.ui.View):
    def __init__(self, char_name: str, owner_id: str):
        super().__init__(timeout=None)
        self.char_name = char_name
        self.owner_id = owner_id

    @discord.ui.button(label="Base Stats", style=discord.ButtonStyle.primary, row=0)
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditStatsModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Equipment", style=discord.ButtonStyle.primary, row=0)
    async def btn_equips(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditEquipsModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Ability", style=discord.ButtonStyle.primary, row=0)
    async def btn_ability(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditAbilityModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Choc Ratings", style=discord.ButtonStyle.primary, row=0)
    async def btn_chocs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditChocsModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Trap & Race Stats", style=discord.ButtonStyle.primary, row=1)
    async def btn_trap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditTrapStatsModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Quirks & Whims", style=discord.ButtonStyle.primary, row=1)
    async def btn_quirks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditQuirksModal(self.char_name, self.owner_id))

    @discord.ui.button(label="Add/Edit Magic", style=discord.ButtonStyle.primary, row=1)
    async def btn_magic(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditMagicModal(self.char_name, self.owner_id))

@bot.tree.command(name="editsheet", description="Open the Character Builder Dashboard")
@app_commands.describe(target="Specific character (Defaults to Active)")
@app_commands.autocomplete(target=target_auto)
async def cmd_editsheet(interaction: discord.Interaction, target: str = None):
    char_name = target if target else get_active_name(interaction)
    if target and not validate_target(interaction, char_name):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)
    
    owner_id = None
    for p_uid, pdata in db["players"].items():
        if p_uid.endswith(f"_{interaction.guild_id}") and "characters" in pdata and char_name in pdata["characters"]:
            owner_id = p_uid
            break
            
    if not owner_id: return await interaction.response.send_message("âŒ Character not found.", ephemeral=True)
    
    view = CharacterBuilderView(char_name, owner_id)
    await interaction.response.send_message(f"âš™ï¸ Editing **{char_name}**:", view=view, ephemeral=True)



# --- Inventory Management Commands ---
@bot.tree.command(name="giveitem", description="Add an item to a character's inventory")
@app_commands.autocomplete(item_name=global_item_auto, target=target_auto)
@app_commands.describe(
    quantity="Number of items to give", 
    preference="Optional: Character preference for this item",
    target="Optional: Which character receives this? (Defaults to active)",
    uses="Optional: Give a partially used item with this many uses left"
)
@app_commands.choices(preference=[
    app_commands.Choice(name="Obsessed (+2)", value="Obsessed"),
    app_commands.Choice(name="Well-Liked (+1)", value="Well-Liked"),
    app_commands.Choice(name="Neutral (0)", value="Neutral"),
    app_commands.Choice(name="Disliked (-1)", value="Disliked"),
    app_commands.Choice(name="Allergic (-2)", value="Allergic")
])
async def cmd_giveitem(interaction: discord.Interaction, item_name: str, quantity: int = 1, preference: str = "Neutral", target: str = None, uses: int = None):
    char_name = target if target else get_active_name(interaction)
    if not can_edit(interaction, char_name):
        return await interaction.response.send_message("âŒ You do not have permission to edit this character.", ephemeral=True)
    
    group, key, base_data = get_item_base_data(item_name)
    display_title = base_data.get("title", item_name.title()) if base_data else item_name.title()
    max_uses = parse_uses(base_data.get("uses", "1")) if base_data else 1
    
    if uses is not None and (uses <= 0 or (isinstance(max_uses, int) and uses > max_uses)):
        return await interaction.response.send_message(f"âŒ Invalid uses provided. Must be between 1 and {max_uses}.", ephemeral=True)

    success, msg = grant_item(char_name, display_title, quantity, max_uses, preference, starting_uses=uses, guild_id=str(interaction.guild_id))
    if success:
        return await interaction.response.send_message(f"ðŸŽ’ Added **{quantity}x {display_title}** (Pref: {preference}) to **{char_name}**'s inventory!", ephemeral=True)
    else:
        return await interaction.response.send_message(f"âŒ {msg}", ephemeral=True)

@bot.tree.command(name="takeitem", description="Remove an item from a character's inventory")
@app_commands.autocomplete(item_name=char_item_auto, target=target_auto)
async def cmd_takeitem(interaction: discord.Interaction, item_name: str, target: str = None):
    char_name = target if target else get_active_name(interaction)
    if not can_edit(interaction, char_name):
        return await interaction.response.send_message("âŒ You do not have permission to edit this character.", ephemeral=True)
        
    guild_id = str(interaction.guild_id)
    if char_name.startswith("Storage: "):
        party_name = char_name[9:]
        if guild_id in db.get("wallet", {}) and party_name in db["wallet"][guild_id].get("parties", {}):
            inv = db["wallet"][guild_id]["parties"][party_name].get("storage", {})
            instances = {i_uid: data for i_uid, data in inv.items() if data.get("name", i_uid).lower() == item_name.lower()}
            
            if not instances:
                return await interaction.response.send_message(f"âš ï¸ **{char_name}** does not have **{item_name}**.", ephemeral=True)
                
            if len(instances) == 1:
                target_uid = list(instances.keys())[0]
                await process_item_use(interaction, char_name, char_name, None, target_uid, action="take", use_times=1, guild_id=guild_id)
            else:
                view = ItemInstanceView(char_name, char_name, None, item_name, instances, action="take", use_times=1, guild_id=guild_id)
                await interaction.response.send_message("You have multiple instances of this item.", view=view, ephemeral=True)
            return
        else:
            return await interaction.response.send_message("âŒ Party storage not found.", ephemeral=True)

    for uid, pdata in db["players"].items():
        if "characters" in pdata and char_name in pdata["characters"]:
            inv = pdata["characters"][char_name].get("inventory", {})
            instances = {i_uid: data for i_uid, data in inv.items() if data.get("name", i_uid).lower() == item_name.lower()}
            
            if not instances:
                return await interaction.response.send_message(f"âš ï¸ **{char_name}** does not have **{item_name}**.", ephemeral=True)
                
            if len(instances) == 1:
                target_uid = list(instances.keys())[0]
                await process_item_use(interaction, char_name, char_name, uid, target_uid, action="take")
            else:
                view = ItemInstanceView(char_name, char_name, uid, item_name, instances, action="take")
                await interaction.response.send_message("You have multiple instances of this item.", view=view, ephemeral=True)

@bot.tree.command(name="useitem", description="Use an item and view its effects")
@app_commands.autocomplete(item_name=char_item_auto, target=target_auto)
@app_commands.describe(
    item_name="The name of the item to use",
    target="Optional: Pick a target to use the item on",
    use_times="Optional: How many times to use this item (Default: 1)"
)
async def cmd_useitem(interaction: discord.Interaction, item_name: str, target: str = None, use_times: int = 1):
    author_char = get_active_name(interaction)
    if not author_char:
        return await interaction.response.send_message("âŒ You must have an active character to use an item.", ephemeral=True)
        
    if use_times <= 0:
        return await interaction.response.send_message("âŒ `use_times` must be greater than 0.", ephemeral=True)

    target_char = target if target else author_char
    if target and not validate_target(interaction, target_char):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)

    author_uid = f"{interaction.user.id}_{interaction.guild_id}"
    if author_uid not in db["players"] or "characters" not in db["players"][author_uid] or author_char not in db["players"][author_uid]["characters"]:
        return await interaction.response.send_message("âŒ Your active character is not valid.", ephemeral=True)

    inv = db["players"][author_uid]["characters"][author_char].get("inventory", {})
    
    # Filter instances to only those that have enough uses
    instances = {}
    for i_uid, data in inv.items():
        if data.get("name", i_uid).lower() == item_name.lower():
            u = data.get("uses", 1)
            if isinstance(u, str) or u >= use_times:
                instances[i_uid] = data

    if not instances:
        return await interaction.response.send_message(f"âš ï¸ **{author_char}** does not have **{item_name}** with at least {use_times} uses left.", ephemeral=True)

    if len(instances) == 1:
        target_uid = list(instances.keys())[0]
        await process_item_use(interaction, target_char, author_char, author_uid, target_uid, action="use", use_times=use_times)
    else:
        view = ItemInstanceView(target_char, author_char, author_uid, item_name, instances, action="use", use_times=use_times)
        await interaction.response.send_message(f"You have multiple instances with enough uses. Select one:", view=view, ephemeral=True)

# ==========================================
# PLAYER HELP & LOOKUP COMMANDS
# ==========================================
async def send_chunked_message(interaction: discord.Interaction, text: str):
    """Splits a long message into 1900-character chunks and sends them sequentially."""
    # We must respond to the interaction first, then follow up
    lines = text.split('\n')
    chunks = []
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > 1900:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
            
    if current_chunk:
        chunks.append(current_chunk)
        
    await interaction.response.send_message(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@bot.tree.command(name="status", description="Look up a specific status effect (Full Mechanics)")
@app_commands.autocomplete(group=status_group_auto, name=status_name_auto)
async def cmd_status(interaction: discord.Interaction, group: str, name: str):
    try:
        data = db["statuses"][group][name]
        char_name = get_active_name(interaction)
        
        display_title = data.get("title", name.title())
        effect = data.get("effect", "No effect provided.")
        flavor = data.get("text", "").replace("_", char_name)
        
        body = f"**Group:** {group}\n**Effect:**\n{effect}"
        if flavor:
            body += f"\n\n*Text: {flavor}*"
            
        embed_color = discord.Color.light_grey()
        if "good" in group.lower(): embed_color = discord.Color.green()
        elif "bad" in group.lower(): embed_color = discord.Color.red()
            
        embed = discord.Embed(title=display_title, description=body, color=embed_color)
        
        if data.get("variants"):
            view = VariantView("statuses", group, display_title, data, embed_color)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
    except KeyError:
        await interaction.response.send_message("Status not found.", ephemeral=True)

@bot.tree.command(name="item", description="Look up a specific item (Full Mechanics)")
@app_commands.autocomplete(group=item_group_auto, name=item_name_auto)
async def cmd_item(interaction: discord.Interaction, group: str, name: str):
    try:
        data = db["items"][group][name]
        char_name = get_active_name(interaction)
        
        display_title = data.get("title", name.title())
        uses = data.get("uses", "1")
        effect = data.get("effect", "No effect provided.")
        flavor = data.get("description", "").replace("_", char_name)
        
        body = f"**Group:** {group}\n**Uses:** {uses}\n**Effect:**\n{effect}"
        if flavor:
            body += f"\n\n*Description: {flavor}*"
            
        embed = discord.Embed(title=display_title, description=body, color=discord.Color.blue())
        
        if data.get("variants"):
            view = VariantView("items", group, display_title, data, discord.Color.blue())
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed)
    except KeyError:
        await interaction.response.send_message("Item not found.", ephemeral=True)

async def help_command_auto(interaction: discord.Interaction, current: str):
    commands = [
        "addchar", "setchar", "removechar", "movesheet", "editpreference", "editsheet",
        "removemagic", "giveitem", "takeitem", "useitem", "party", "storage", 
        "shop", "upgrade", "item", "status", "badge", "randomitem", "randomstatus",
        "creategroup", "editgroup", "removegroup", "additem", "additemvariant", "edititem", 
        "edititemvariant", "removeitem", "addstatus", "addstatusvariant", "editstatus", 
        "editstatusvariant", "removestatus", "backup", "dmtargetscope", "help", "characterlist player", 
        "characterlist party", "joinparty", "leaveparty", "clearinventory"
    ]
    import discord.app_commands as app_commands
    return [app_commands.Choice(name=f"/{c}", value=c) for c in commands if current.lower() in c.lower()][:25]

@bot.tree.command(name="help", description="View the Amaranth Archive guide and command help")
@app_commands.describe(command_name="The specific command you need help with")
@app_commands.autocomplete(command_name=help_command_auto)
async def cmd_help(interaction: discord.Interaction, command_name: str = None):
    if not command_name:
        desc = (
            "**Welcome to the Amaranth Archive!**\n"
            "Below is a complete list of all commands available to you. For deeper mechanics on any specific command, run `/help` and type its name into the optional box!\n\n"
            "ðŸ‘¤ **Character & Stat Management**\n"
            "`/addchar`, `/setchar`, `/removechar`, `/movesheet`, `/editsheet`, `/removemagic`, `/editpreference`, `/joinparty`, `/leaveparty`\n\n"
            "ðŸŽ’ **Inventory, Economy & Upgrades**\n"
            "`/giveitem`, `/takeitem`, `/useitem`, `/storage`, `/shop`\n\n"
            "ðŸ“– **Lookup & Game Information**\n"
            "`/item`, `/status`, `/badge`, `/randomitem`, `/randomstatus`, `/help`, `/characterlist player`, `/characterlist party` \n\n"
            "ðŸ‘‘ **DM & Game Data Management**\n"
            "`/dmtargetscope`, `/creategroup`, `/editgroup`, `/removegroup`, `/additem`, `/additemvariant`, `/edititem`, `/edititemvariant`, `/removeitem`, `/addstatus`, `/addstatusvariant`, `/editstatus`, `/editstatusvariant`, `/removestatus`, `/backup`, `/party`, `/upgrade`, `/clearinventory`"
        )
        embed = discord.Embed(title="Amaranth Archive Command List", description=desc, color=discord.Color.blue())
        return await interaction.response.send_message(embed=embed)

    c = command_name.lower().replace("/", "")

    help_dict = {
        "addchar": "Adds a new character tied to your discord account! This character's sheet can be edited when added and with the `/editsheet` command.",
        "setchar": "Switches your current active character to another registered one! You can still edit your other characters in other ways, but your active character becomes the default one when editing other character commands. (For example, if you have two characters named Leafen and Glacia, and Leafen is the one selected, you can still use /setstats to edit both of their stats by directly inputting their name. However, if you use the command without inputting a specific character's name, it will always default to Leafen.)",
        "removechar": "Removes a character from your roster! This deletes all data involved with the character, including their inventory. If you choose to remove a character from your roster, please use `/storage` to deposit all ITEMs from their inventory into storage for other characters to use.",
        "movesheet": "View the complete stat sheet of one of your characters! With this, you can check their Base Stats, MAGICs, Inventory, Trap and Race stats, and Preferences.",
        "editsheet": "Lets you edit nearly everything about your character sheet! This contains the ability to change your Base Stats, Equipment, Ability, Chocolate Ratings, Trap & Race Stats, Quirks & Whims, and Add/Edit Magic!",
        "giveitem": "Adds an ITEM to a character's inventory! This is usually done if you get a dropped ITEM from battle. If there are multiple characters in that battle, make sure to decide who gets what before giving out ITEMs. If you need help adding or figuring distribution out, ask an Admin.",
        "takeitem": "Removes an ITEM from a character's inventory! This is usually done if an enemy steals and uses up an ITEM. **Important Note:** Do not use this command if you intend on using an ITEM for its effect; instead, use the `/useitem` command. If an ITEM with multiple uses is discarded by `/takeitem`, all uses of it will disappear.",
        "useitem": "Use an ITEM from your character's inventory! This not only removes 1 use of the ITEM from it, but also displays the effect of the ITEM as well for others to see.",
        "shop": "Views the shops for each ITEM group and badges, and lets you buy from them! Admins can also lock certain items for progression or being 'out of stock'.",
        "upgrade": "Manages permanent character upgrades! This means it changes the amount of Crystal Hearts you have and if you have a Dimensional Satchel or not. Only the Admins can access this command.",
        "help": "Surprisingly, you're already there! To view the command list, type `/help` without filling out the optional field! If you just want to say hi, then there is a button for you to do so!",
        "badge": "Look up a specific Badge! Badges are equips like Weapons and Armor, but unlike those two, it is generic and can be equipped by any character. Please note that all Badges on a character must be unique; you cannot have 2 or more of the same Badge on them. Also, each character can only have up to one Combo Badge OR Emblem; not both at the same time, and not more than one of each. The Badge groups are below.\n\nNormal Badges: Badges that can be equipped immediately when bought. There are 43 Normal Badges, which consist of:\nAgility, Aggressive Armament, Awareness, Axe-Load, Cleaning, Deep Concentration, Deep Focus, Dexterity, Fortunate, Fruity, Fury, Grindgame, Hail, Hard Hitter, Headstart, Heart Finder I, Heart Finder II, Heart Finder III, Heart Finder IV, Heavy, Helmet, Intelligence, Invigorated, Lifesaver, Lucky, Medical, Nightlight, Pay-Off, Quick Defend, Quick Eater, Quick Reflexes, Rounder, Serenity, Speed, Spoon, Strength, Survivalist, Teamwork, Thorny, Tower, Vengeance, Vigilante, Vixen, Weak Point, and Wish.\n\nCombo Badges: Badges that consist of 3 different badges to combine into. There are 5 Normal Badges, which consist of:\nFirst-Aid: Medical Badge, Spoon Badge, and Quick Eater Badge.\nHigh Roller: Hail Badge, Headstart Badge, Vixen Badge.\nMultiplier: Heavy Badge, Lucky Badge, Weak Point Badge.\nRejuvenation: Awareness Badge, Invigorated Badge, Lifesaver Badge.\nRPG: Dexterity Badge, Intelligence Badge, Strength Badge\n\nEmblems: Special Badges that cannot be bought and can only be obtained as a reward for completing a battle or Bounty. There are 14 Emblems, which consist of:\nAnxiety, Comboing, Divinity, Endless Rage, Foliage, Fame, Fortune, Frights, Gold, Ribbits, Technology, the SOUL, Tranquility, and Warriors.",
        "randomitem": "Roll for a random ITEM! There is a field to pick a specific group of ITEMs to roll from; all ITEMs in that group have an equal chance. The ITEM groups you can roll from contains:\nAny Non-Special, Food, Drink, Battle, Revive, or Special.",
        "randomstatus": "Roll for a random STATUS! There is a field to pick a specific group of STATUSes to roll from; all STATUSes in that group have an equal chance. If you choose Any Random, you roll for a random group and must use the command again with that group. The STATUS groups you can roll from contains:\nGood, Neutral, and Bad.",
        "creategroup":"Creates a new STATUS or ITEM group to sort STATUSes and ITEMs in!",
        "editgroup": "Edits an existing group's description!",
        "removegroup": "Removes an existing group completely! **IMPORTANT:** This also removes all ITEMs and STATUSes in that group.",
        "additem": "Creates a new ITEM!",
        "additemvariant": "Creates a new variant of an ITEM! Existing variants are Well-Liked and Obsessed.",
        "edititem": "Edits the name, uses, effect, and description of an existing item!",
        "edititemvariant": "Edits the name, uses, effect, and description of an existing item variant!",
        "removeitem": "Removes an existing ITEM and its variants completely!",
        "dmtargetscope": "Lets an Admin change the names in the autocomplete for Party Member fields! This can change between Global, Party-Specific, or your Own characters.",
        "addstatus": "Creates a new STATUS!",
        "addstatusvariant": "Creates a new variant of a STATUS! Currently, there are none, but there might be in the future.",
        "editstatus": "Edits the name, effect, and text for an existing STATUS!",
        "editstatusvariant": "Edits the name, effect, and text for an existing STATUS variant!",
        "removestatus": "Removes an existing STATUS and its variants completely!",
        "backup": "Downloads the bot's raw `.json` databases; used to keep a backup safe in case something goes wrong in the future.",
        "party": "Manages the server's party, active characters within the party, and the server's currency. Only the Admins can access this command.",
        "storage": "Lets you view your party's storage! You can also deposit or withdraw ITEMs from it.",
        "editpreferences": "Edit your character's ITEM preferences! Whenever adding an ITEM to your inventory, check to see what your preference is to add any Well-Liked or Obsessed variants directly to your inventory. Disliked ITEMs heal half HP, deal double damage, or have their effects halved (if neither of the previous effects apply). Allergic ITEMs do nothing but afflict the target with ALLERGIC for 3 turns.",
        "characterlist player": "Lets you see a list of your characters! Please note that characters are server-specific.",
        "characterlist party": "Lets you see a list of characters in a party!",
        "joinparty": "Lets a character join a party made in the server! This lets you use commands that relate to other people in the same party (like use ITEMs on another person's character, for instance).",
        "leaveparty": "Lets you remove your character from a party it is in! The party will be sad to see you go...",
        "clearinventory": "Allows an Admin to clear the entire inventory of one character, a party's storage, or everyone in a party!"
    }

    # Groups logic decoupled for independent help texts
    if c in ["item", "status"]:
        
            
        category = "statuses" if "status" in c else "items" if "item" in c else "badges"
        
        group_lines = []
        for g_name, g_desc in db["groups"][category].items():
            g_items = [v.get("title", k.title()) for k, v in db[category].get(g_name, {}).items()]
            items_str = f" which consist of:\n{', '.join(sorted(g_items))}." if g_items else ""
            group_lines.append(f"**{g_name}**: {g_desc}{items_str}")
            
        groups_joined = "\n\n".join(group_lines) if group_lines else "*(No groups created yet. Ask DM to use /creategroup)*"
        
        if c == "item":
            group_lines = []
            for g_name, g_desc in db["groups"]["items"].items():
                g_items = [v.get("title", k.title()) for k, v in db["items"].get(g_name, {}).items()]
                count = len(g_items)
                type_name = "Golden" if g_name.lower() == "special" else g_name
                items_str = f" There are {count} {type_name} ITEMs, which consist of:\n{', '.join(sorted(g_items))}." if g_items else ""
                group_lines.append(f"**{g_name}**: {g_desc}{items_str}")
            
            groups_joined = "\n\n".join(group_lines) if group_lines else "*(No groups created yet. Ask DM to use /creategroup)*"
            
            msg = f"**Command: `/item`**\nLooks up a specific ITEM! These give a wonderful range of effects, from healing up your Party to crippling the enemy! The ITEM groups are below.\n\n{groups_joined}"
            return await send_chunked_message(interaction, msg)
            
        elif c == "status":
            msg = f"**Command: `/status`**\nLook up a specific STATUS! These are effects that can greatly increase or decrease one's combat ability! The STATUS groups are below.\n\n{groups_joined}"
            return await send_chunked_message(interaction, msg)

    if c in help_dict:
        embed = discord.Embed(title=f"Command Help: `/{c}`", description=help_dict[c], color=discord.Color.green())
        if c == "help":
            return await interaction.response.send_message(embed=embed, view=HelpView())
        return await interaction.response.send_message(embed=embed)
        
    if c.startswith("add") or c.startswith("edit") or c.startswith("remove") or c == "creategroup":
        embed = discord.Embed(title=f"Command Help: `/{c}`", description="This is a DM-only Game Data Management command. Use it to build and manage the bot's custom database elements (Groups, Items, Statuses, Variants).", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed)

    await interaction.response.send_message(f"No detailed help available for **/{c}** yet.", ephemeral=True)

class RandomStatusView(discord.ui.View):
    def __init__(self, statustype: str, target: str):
        super().__init__(timeout=None)
        self.statustype = statustype
        self.target = target
        
    @discord.ui.button(label="Reroll ðŸŽ²", style=discord.ButtonStyle.primary, custom_id="btn_status_reroll")
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        import random
        pool, weights = [], []
        for g_name, statuses in db["statuses"].items():
            if self.statustype.lower() == g_name.lower():
                for s_id, s_data in statuses.items():
                    pool.append((g_name, s_id, s_data))
                    weights.append(s_data.get("weight", 1.0))
                    
        if not pool: return await interaction.response.send_message("No statuses found in that group.", ephemeral=True)
            
        random_group, random_id, data = random.choices(pool, weights=weights, k=1)[0]
        char_name = self.target if self.target else get_active_name(interaction)
        
        display_title = data.get("title", random_id.title())
        flavor = data.get("text", "").replace("_", char_name)
        effect = data.get("effect", "No effect provided.")
        
        subject = char_name if char_name != interaction.user.display_name else "You"
        verb = "was" if subject != "You" else "were"
        
        desc = f"**{subject} {verb} afflicted with {display_title}!**\n\n**Group:** {random_group}\n**Effect:**\n{effect}"
        if flavor: desc += f"\n\n*Text: {flavor}*"
        
        embed_color = discord.Color.light_grey()
        if "good" in random_group.lower(): embed_color = discord.Color.green()
        elif "bad" in random_group.lower(): embed_color = discord.Color.red()
            
        embed = discord.Embed(description=desc, color=embed_color)
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="randomstatus", description="Roll a random status effect")
@app_commands.autocomplete(statustype=statustype_auto, target=target_auto)
@app_commands.describe(
    statustype="Filter by group",
    target="Optional: Pick a specific character to afflict"
)

async def cmd_randomstatus(interaction: discord.Interaction, statustype: str, target: str = None):
    if not statustype:
        group_lines = []
        for g_name, g_desc in db["groups"]["statuses"].items():
            g_items = [s_data.get("title", s_id.title()) for s_id, s_data in db["statuses"].get(g_name, {}).items()]
            items_str = f"\nContains: {', '.join(sorted(g_items))}." if g_items else ""
            group_lines.append(f"**{g_name}:** {g_desc}{items_str}")
            
        groups_joined = "\n\n".join(group_lines) if group_lines else "*(No groups created yet. Ask DM to use /creategroup)*"
        
        msg = f"To use this command, you must select one of the following groups and hope your luck is good. The groups are as follows:\n\n**Random Type:** Chooses Good, Neutral, or Bad at random. Only use if an effect rolls a truly random STATUS instead of one from a specific group. After you get your group, run this command again and select that group to get your STATUS.\n\n{groups_joined}"
        return await send_chunked_message(interaction, msg)

    if statustype.lower() == "random":
        roll = random.choices(["Good", "Neutral", "Bad"], weights=[40, 20, 40], k=1)[0]
        flavor_text = f"Interesting... You got a **{roll}** STATUS. Run this command again and pick the {roll} group."
        if roll == "Bad": flavor_text = f"Uh-oh... You got a **{roll}** STATUS... Run this command again and pick the {roll} group..."
        elif roll == "Good": flavor_text = f"Congrats! You got a **{roll}** STATUS! Run this command again and pick the {roll} group!"
        return await interaction.response.send_message(flavor_text)

    pool, weights = [], []
    for g_name, statuses in db["statuses"].items():
        if statustype.lower() == g_name.lower():
            for s_id, s_data in statuses.items():
                pool.append((g_name, s_id, s_data))
                weights.append(s_data.get("weight", 1.0))
                
    if not pool: return await interaction.response.send_message("No statuses found in that group.", ephemeral=True)
        
    random_group, random_id, data = random.choices(pool, weights=weights, k=1)[0]
    char_name = target if target else get_active_name(interaction)
    
    display_title = data.get("title", random_id.title())
    flavor = data.get("text", "").replace("_", char_name)
    effect = data.get("effect", "No effect provided.")
    
    subject = char_name if char_name != interaction.user.display_name else "You"
    verb = "was" if subject != "You" else "were"
    
    desc = f"**{subject} {verb} afflicted with {display_title}!**\n\n**Group:** {random_group}\n**Effect:**\n{effect}"
    if flavor: desc += f"\n\n*Text: {flavor}*"
    
    embed_color = discord.Color.light_grey()
    if "good" in random_group.lower(): embed_color = discord.Color.green()
    elif "bad" in random_group.lower(): embed_color = discord.Color.red()
        
    embed = discord.Embed(description=desc, color=embed_color)
    view = RandomStatusView(statustype, target)
    await interaction.response.send_message(embed=embed, view=view)

class RandomItemView(discord.ui.View):
    def __init__(self, itemgroup: str, target: str):
        super().__init__(timeout=None)
        self.itemgroup = itemgroup
        self.target = target
        
    @discord.ui.button(label="Reroll ðŸŽ²", style=discord.ButtonStyle.primary, custom_id="btn_item_reroll")
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        import random
        pool, weights = [], []
        for g_name, items in db["items"].items():
            if self.itemgroup.lower() == "any non-special":
                if g_name.lower() not in ["special", "special items", "special_items"]:
                    for i_id, i_data in items.items():
                        pool.append((g_name, i_id, i_data))
                        weights.append(i_data.get("weight", 1.0))
            elif self.itemgroup.lower() == g_name.lower():
                for i_id, i_data in items.items():
                    pool.append((g_name, i_id, i_data))
                    weights.append(i_data.get("weight", 1.0))
                
        if not pool: return await interaction.response.send_message("No items found in that group.", ephemeral=True)
            
        random_group, random_id, data = random.choices(pool, weights=weights, k=1)[0]
        char_name = self.target if self.target else get_active_name(interaction)
        
        display_title = data.get("title", random_id.title())
        uses = data.get("uses", "1")
        flavor = data.get("description", "").replace("_", char_name)
        effect = data.get("effect", "No effect provided.")
        
        subject = char_name if char_name != interaction.user.display_name else "You"
        
        desc = f"**{subject} obtained: {display_title}!**\n\n**Group:** {random_group}\n**Uses:** {uses}\n**Effect:**\n{effect}"
        if flavor: desc += f"\n\n*Description: {flavor}*"
        
        embed = discord.Embed(description=desc, color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="randomitem", description="Roll a random item")
@app_commands.autocomplete(itemgroup=itemtype_auto, target=target_auto)
@app_commands.describe(
    itemgroup="Filter by group",
    target="Optional: Pick a specific character to receive the item"
)

async def cmd_randomitem(interaction: discord.Interaction, itemgroup: str, target: str = None):
    if not itemgroup:
        group_lines = []
        for g_name, g_desc in db["groups"]["items"].items():
            g_items = [i_data.get("title", i_id.title()) for i_id, i_data in db["items"].get(g_name, {}).items()]
            items_str = f" Contains: {', '.join(sorted(g_items))}." if g_items else ""
            group_lines.append(f"**{g_name}:** {g_desc}{items_str}")
            
        groups_joined = "\n\n".join(group_lines) if group_lines else "*(No groups created yet. Ask DM to use /creategroup)*"
        
        msg = f"To use this command, you must select one of the following groups and pick an ITEM from it. The groups are as follows:\n\n{groups_joined}"
        return await send_chunked_message(interaction, msg)

    pool, weights = [], []
    for g_name, items in db["items"].items():
        if itemgroup.lower() == "any non-special":
            if g_name.lower() not in ["special", "special items", "special_items"]:
                for i_id, i_data in items.items():
                    pool.append((g_name, i_id, i_data))
                    weights.append(i_data.get("weight", 1.0))
        elif itemgroup.lower() == g_name.lower():
            for i_id, i_data in items.items():
                pool.append((g_name, i_id, i_data))
                weights.append(i_data.get("weight", 1.0))
            
    if not pool: return await interaction.response.send_message("No items found in that group.", ephemeral=True)
        
    random_group, random_id, data = random.choices(pool, weights=weights, k=1)[0]
    char_name = target if target else get_active_name(interaction)
    
    display_title = data.get("title", random_id.title())
    uses = data.get("uses", "1")
    flavor = data.get("description", "").replace("_", char_name)
    effect = data.get("effect", "No effect provided.")
    
    subject = char_name if char_name != interaction.user.display_name else "You"
    
    desc = f"**{subject} obtained: {display_title}!**\n\n**Group:** {random_group}\n**Uses:** {uses}\n**Effect:**\n{effect}"
    if flavor: desc += f"\n\n*Description: {flavor}*"
    
    embed = discord.Embed(description=desc, color=discord.Color.gold())
    view = RandomItemView(itemgroup, target)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="badge", description="Look up a specific badge (Full Mechanics)")
@app_commands.autocomplete(group=badge_group_auto, name=badge_name_auto)
async def cmd_badge(interaction: discord.Interaction, group: str, name: str):
    try:
        data = db["badges"][group][name]
        
        display_title = data.get("title", name.title())
        effect = data.get("effect", "No effect provided.")
        
        body = f"**Category:** {group}\n\n**Effect:**\n{effect}"
            
        embed = discord.Embed(title=f"ðŸ›¡ï¸ {display_title}", description=body, color=discord.Color.dark_theme())
        await interaction.response.send_message(embed=embed)
    except KeyError:
        await interaction.response.send_message("Badge not found.", ephemeral=True)

# ==========================================
# ADMIN / DM COMMANDS (Groups, Modals, Edits)
# ==========================================
@bot.tree.command(name="creategroup", description="DM Only: Create a new item or status group")
@app_commands.describe(
    category="Is this for Items or Statuses?",
    name="Name of the group (e.g. Good, items-group-one). Case is preserved!",
    description="Description of the group (appears in the random roll help info)"
)
@app_commands.choices(category=[
    app_commands.Choice(name="Status Group", value="statuses"),
    app_commands.Choice(name="Item Group", value="items")
])
async def cmd_creategroup(interaction: discord.Interaction, category: str, name: str, description: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    if name in db["groups"][category]:
        return await interaction.response.send_message(f"âš ï¸ Group **{name}** already exists!", ephemeral=True)
        
    db["groups"][category][name] = description
    if name not in db[category]:
        db[category][name] = {}
        
    save_data("groups", db["groups"])
    save_data(category, db[category])
    await interaction.response.send_message(f"âœ… Created new {category[:-2]} group: **{name}**!", ephemeral=True)

@bot.tree.command(name="editgroup", description="DM Only: Edit an existing group's description")
@app_commands.describe(name="Name of the group EXACTLY as it appears", description="New description")
@app_commands.choices(category=[
    app_commands.Choice(name="Status Group", value="statuses"),
    app_commands.Choice(name="Item Group", value="items")
])
async def cmd_editgroup(interaction: discord.Interaction, category: str, name: str, description: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    if name not in db["groups"][category]:
        return await interaction.response.send_message(f"âš ï¸ Group **{name}** does not exist. Remember, names are case-sensitive!", ephemeral=True)
        
    db["groups"][category][name] = description
    save_data("groups", db["groups"])
    await interaction.response.send_message(f"âœ… Updated **{name}** description!", ephemeral=True)

@bot.tree.command(name="removegroup", description="DM Only: Remove a group ENTIRELY (Deletes all entries inside it!)")
@app_commands.describe(name="Name of the group EXACTLY as it appears")
@app_commands.choices(category=[
    app_commands.Choice(name="Status Group", value="statuses"),
    app_commands.Choice(name="Item Group", value="items")
])
async def cmd_removegroup(interaction: discord.Interaction, category: str, name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    if name in db["groups"][category]:
        del db["groups"][category][name]
        save_data("groups", db["groups"])
        
    if name in db[category]:
        del db[category][name]
        save_data(category, db[category])
        
    await interaction.response.send_message(f"ðŸ—‘ï¸ Group **{name}** and all its contents have been removed.", ephemeral=True)

class AddEntryModal(discord.ui.Modal):
    def __init__(self, category: str, group: str, entry_id: str, display_title: str, uses: str = None):
        clean = "Status" if category == "statuses" else "Item"
        super().__init__(title=f"Add {clean}")
        self.category = category
        self.group = group
        self.entry_id = entry_id
        self.display_title = display_title
        self.uses = uses

        self.effect_text = discord.ui.TextInput(
            label="Mechanical Effect",
            style=discord.TextStyle.paragraph, max_length=4000,
            placeholder="Heals 30 HP / Flips a coin...",
            required=True
        )
        
        flavor_label = "Description (Use _ for char)" if category == "items" else "Text (Use _ for char)"
        self.flavor_text = discord.ui.TextInput(
            label=flavor_label,
            style=discord.TextStyle.paragraph, max_length=4000,
            placeholder="_ is going berserk!",
            required=False
        )
        
        self.aliases = discord.ui.TextInput(
            label="Aliases (Comma-separated)",
            style=discord.TextStyle.short,
            required=False
        )
        self.drop_weight = discord.ui.TextInput(
            label="Drop Weight (Default: 1.0)",
            style=discord.TextStyle.short,
            placeholder="1.0",
            required=False
        )

        self.add_item(self.effect_text)
        self.add_item(self.flavor_text)
        self.add_item(self.aliases)
        self.add_item(self.drop_weight)

    async def on_submit(self, interaction: discord.Interaction):
        if self.group not in db["groups"][self.category]:
            return await interaction.response.send_message(f"âŒ Group `{self.group}` does not exist. Please use `/creategroup` first!", ephemeral=True)
            
        if self.group not in db[self.category]: db[self.category][self.group] = {}
            
        alias_list = [a.strip().lower() for a in self.aliases.value.split(",") if a.strip()]
        try: weight_val = float(self.drop_weight.value) if self.drop_weight.value else 1.0
        except ValueError: weight_val = 1.0 

        flavor_key = "description" if self.category == "items" else "text"

        db[self.category][self.group][self.entry_id] = {
            "title": self.display_title,
            "effect": self.effect_text.value,
            flavor_key: self.flavor_text.value, 
            "aliases": alias_list,
            "weight": weight_val
        }
        
        if self.category == "items" and self.uses is not None:
            db[self.category][self.group][self.entry_id]["uses"] = self.uses
            
        save_data(self.category, db[self.category])
        await interaction.response.send_message(f"âœ… Added **{self.display_title}** to `{self.group}`!", ephemeral=True)

class EditEntryModal(discord.ui.Modal):
    def __init__(self, category: str, group: str, entry_id: str, data: dict):
        clean = "Status" if category == "statuses" else "Item"
        super().__init__(title=f"Edit {clean}: {entry_id[:15]}")
        self.category = category
        self.group = group
        self.entry_id = entry_id
        self.data = data

        self.display_title = discord.ui.TextInput(
            label="Display Title",
            style=discord.TextStyle.short,
            default=data.get("title", entry_id.title()),
            required=True
        )
        self.effect_text = discord.ui.TextInput(
            label="Mechanical Effect",
            style=discord.TextStyle.paragraph, max_length=4000,
            default=data.get("effect", ""),
            required=True
        )
        
        flavor_key = "description" if category == "items" else "text"
        flavor_label = "Description (Use _ for char)" if category == "items" else "Text (Use _ for char)"
        self.flavor_text = discord.ui.TextInput(
            label=flavor_label,
            style=discord.TextStyle.paragraph, max_length=4000,
            default=data.get(flavor_key, ""),
            required=False
        )
        self.aliases = discord.ui.TextInput(
            label="Aliases (Comma-separated)",
            style=discord.TextStyle.short,
            default=", ".join(data.get("aliases", [])),
            required=False
        )
        self.drop_weight = discord.ui.TextInput(
            label="Drop Weight",
            style=discord.TextStyle.short,
            default=str(data.get("weight", 1.0)),
            required=False
        )

        self.add_item(self.display_title)
        self.add_item(self.effect_text)
        self.add_item(self.flavor_text)
        self.add_item(self.aliases)
        self.add_item(self.drop_weight)

    async def on_submit(self, interaction: discord.Interaction):
        alias_list = [a.strip().lower() for a in self.aliases.value.split(",") if a.strip()]
        try: weight_val = float(self.drop_weight.value) if self.drop_weight.value else 1.0
        except ValueError: weight_val = 1.0

        flavor_key = "description" if self.category == "items" else "text"
        variants = self.data.get("variants", {})
        uses = self.data.get("uses", "1")

        db[self.category][self.group][self.entry_id] = {
            "title": self.display_title.value,
            "effect": self.effect_text.value,
            flavor_key: self.flavor_text.value,
            "aliases": alias_list,
            "weight": weight_val
        }
        
        if self.category == "items":
            db[self.category][self.group][self.entry_id]["uses"] = uses
            
        if variants:
            db[self.category][self.group][self.entry_id]["variants"] = variants

        save_data(self.category, db[self.category])
        await interaction.response.send_message(f"âœ… Successfully updated **{self.display_title.value}**!", ephemeral=True)


class AddVariantModal(discord.ui.Modal):
    def __init__(self, category: str, group: str, entry_id: str, variant_name: str, variant_data: dict = None, uses: str = None):
        super().__init__(title=f"{'Edit' if variant_data else 'Add'} Variant: {variant_name[:15]}")
        self.category = category
        self.group = group
        self.entry_id = entry_id
        self.variant_name = variant_name
        self.variant_data = variant_data or {}
        self.uses = uses

        self.effect_text = discord.ui.TextInput(
            label="Variant Mechanical Effect",
            style=discord.TextStyle.paragraph, max_length=4000,
            default=self.variant_data.get("effect", ""),
            required=True
        )
        
        flavor_key = "description" if category == "items" else "text"
        flavor_label = "Variant Description" if category == "items" else "Variant Text"
        
        self.flavor_text = discord.ui.TextInput(
            label=flavor_label,
            style=discord.TextStyle.paragraph, max_length=4000,
            default=self.variant_data.get(flavor_key, ""),
            required=False
        )
        self.add_item(self.effect_text)
        self.add_item(self.flavor_text)

    async def on_submit(self, interaction: discord.Interaction):
        if self.group not in db[self.category] or self.entry_id not in db[self.category][self.group]:
            return await interaction.response.send_message("âŒ Base entry not found.", ephemeral=True)
            
        entry = db[self.category][self.group][self.entry_id]
        
        if "variants" not in entry:
            entry["variants"] = {}
            
        flavor_key = "description" if self.category == "items" else "text"
            
        entry["variants"][self.variant_name] = {
            "effect": self.effect_text.value,
            flavor_key: self.flavor_text.value
        }
        
        if self.category == "items":
            if self.uses is not None:
                entry["variants"][self.variant_name]["uses"] = self.uses
            elif self.variant_data and "uses" in self.variant_data:
                entry["variants"][self.variant_name]["uses"] = self.variant_data["uses"]
        
        save_data(self.category, db[self.category])
        action = "Updated" if self.variant_data else "Added"
        await interaction.response.send_message(f"âœ… {action} variant **{self.variant_name}** for `{self.entry_id}`!", ephemeral=True)

@bot.tree.command(name="addstatus", description="DM Only: Add a status")
@app_commands.autocomplete(group=status_group_auto)
async def cmd_addstatus(interaction: discord.Interaction, group: str, id_name: str, display_title: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    await interaction.response.send_modal(AddEntryModal("statuses", group, id_name.lower(), display_title))

@bot.tree.command(name="additem", description="DM Only: Add an item")
@app_commands.autocomplete(group=item_group_auto)
@app_commands.describe(uses="Number of uses (e.g. 1, 3, Infinite)")
async def cmd_additem(interaction: discord.Interaction, group: str, id_name: str, display_title: str, uses: str = "1"):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    await interaction.response.send_modal(AddEntryModal("items", group, id_name.lower(), display_title, uses=uses))

@bot.tree.command(name="additemvariant", description="DM Only: Add a variant to an existing item")
@app_commands.autocomplete(group=item_group_auto, entry_id=item_name_auto)
@app_commands.describe(variant_name="e.g. Well-Liked", uses="Optional: Uses for this variant")
async def cmd_additemvariant(interaction: discord.Interaction, group: str, entry_id: str, variant_name: str, uses: str = None):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    await interaction.response.send_modal(AddVariantModal("items", group, entry_id.lower(), variant_name, uses=uses))

@bot.tree.command(name="addstatusvariant", description="DM Only: Add a variant to an existing status")
@app_commands.autocomplete(group=status_group_auto, entry_id=status_name_auto)
async def cmd_addstatusvariant(interaction: discord.Interaction, group: str, entry_id: str, variant_name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    await interaction.response.send_modal(AddVariantModal("statuses", group, entry_id.lower(), variant_name))

@bot.tree.command(name="edititem", description="DM Only: Edit an existing item")
@app_commands.autocomplete(group=item_group_auto, name=item_name_auto)
@app_commands.describe(new_uses="Optional: Change the amount of uses for this item")
async def cmd_edititem(interaction: discord.Interaction, group: str, name: str, new_uses: str = None):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    name_key = name.lower()
    if group in db["items"] and name_key in db["items"][group]:
        data = db["items"][group][name_key]
        
        if new_uses is not None:
            data["uses"] = new_uses
            save_data("items", db["items"])
            
        await interaction.response.send_modal(EditEntryModal("items", group, name_key, data))
    else:
        await interaction.response.send_message(f"âš ï¸ Could not find **{name_key}** in `{group}`.", ephemeral=True)

@bot.tree.command(name="editstatus", description="DM Only: Edit an existing status")
@app_commands.autocomplete(group=status_group_auto, name=status_name_auto)
async def cmd_editstatus(interaction: discord.Interaction, group: str, name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    name_key = name.lower()
    if group in db["statuses"] and name_key in db["statuses"][group]:
        data = db["statuses"][group][name_key]
        await interaction.response.send_modal(EditEntryModal("statuses", group, name_key, data))
    else:
        await interaction.response.send_message(f"âš ï¸ Could not find **{name_key}** in `{group}`.", ephemeral=True)

@bot.tree.command(name="edititemvariant", description="DM Only: Edit an existing item variant")
@app_commands.autocomplete(group=item_group_auto, name=item_name_auto, variant_name=item_variant_auto)
@app_commands.describe(new_uses="Optional: Change the amount of uses for this variant")
async def cmd_edititemvariant(interaction: discord.Interaction, group: str, name: str, variant_name: str, new_uses: str = None):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    name_key = name.lower()
    if group in db["items"] and name_key in db["items"][group]:
        variants = db["items"][group][name_key].get("variants", {})
        if variant_name in variants:
            if new_uses is not None:
                variants[variant_name]["uses"] = new_uses
                save_data("items", db["items"])
            await interaction.response.send_modal(AddVariantModal("items", group, name_key, variant_name, variants[variant_name]))
        else:
            await interaction.response.send_message(f"âš ï¸ Could not find variant **{variant_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"âš ï¸ Could not find **{name_key}**.", ephemeral=True)

@bot.tree.command(name="editstatusvariant", description="DM Only: Edit an existing status variant")
@app_commands.autocomplete(group=status_group_auto, name=status_name_auto, variant_name=status_variant_auto)
async def cmd_editstatusvariant(interaction: discord.Interaction, group: str, name: str, variant_name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    
    name_key = name.lower()
    if group in db["statuses"] and name_key in db["statuses"][group]:
        variants = db["statuses"][group][name_key].get("variants", {})
        if variant_name in variants:
            await interaction.response.send_modal(AddVariantModal("statuses", group, name_key, variant_name, variants[variant_name]))
        else:
            await interaction.response.send_message(f"âš ï¸ Could not find variant **{variant_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"âš ï¸ Could not find **{name_key}**.", ephemeral=True)

@bot.tree.command(name="removestatus", description="DM Only: Delete a status")
@app_commands.autocomplete(group=status_group_auto, name=status_name_auto)
async def cmd_removestatus(interaction: discord.Interaction, group: str, name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    n = name.lower()
    if group in db["statuses"] and n in db["statuses"][group]:
        del db["statuses"][group][n]
        save_data("statuses", db["statuses"])
        await interaction.response.send_message(f"ðŸ—‘ï¸ Removed **{n}**.", ephemeral=True)

@bot.tree.command(name="removeitem", description="DM Only: Delete an item")
@app_commands.autocomplete(group=item_group_auto, name=item_name_auto)
async def cmd_removeitem(interaction: discord.Interaction, group: str, name: str):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    n = name.lower()
    if group in db["items"] and n in db["items"][group]:
        del db["items"][group][n]
        save_data("items", db["items"])
        await interaction.response.send_message(f"ðŸ—‘ï¸ Removed **{n}**.", ephemeral=True)

@bot.tree.command(name="backup", description="DM Only: Download databases")
async def cmd_backup(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_USER_IDS: return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
    files = [discord.File(f"data/{f}.json") for f in ["items", "statuses", "players", "groups"] if os.path.exists(f"data/{f}.json")]
    if not files: return await interaction.response.send_message("âš ï¸ No files.", ephemeral=True)
    await interaction.response.send_message("ðŸ“¦ Database backup:", files=files, ephemeral=True)



# ==========================================
# PARTY, STORAGE, & SHOP SYSTEM
# ==========================================

def get_active_party(guild_id: str) -> str:
    if guild_id in db["wallet"]:
        return db["wallet"][guild_id].get("active_party", "Main")
    return "Main"

def init_party_if_missing(guild_id: str, party: str):
    if guild_id not in db["wallet"]:
        db["wallet"][guild_id] = {"active_party": "Main", "parties": {}}
    if party not in db["wallet"][guild_id]["parties"]:
        db["wallet"][guild_id]["parties"][party] = {
            "currency_name": "PF",
            "balance": 0,
            "lock_overrides": {},
            "members": [],
            "storage": {}
        }
        save_data("wallet", db["wallet"])
        
def is_item_locked(item_data, guild_id: str, party: str) -> bool:
    default_locked = item_data.get("locked", False)
    if guild_id in db["wallet"] and party in db["wallet"][guild_id].get("parties", {}):
        overrides = db["wallet"][guild_id]["parties"][party].get("lock_overrides", {})
        item_name_lower = item_data["name"].lower()
        if item_name_lower in overrides:
            return overrides[item_name_lower]
    return default_locked

async def shop_category_auto(interaction: discord.Interaction, current: str):
    categories = list(db["shop"].keys())
    return [app_commands.Choice(name=c, value=c) for c in categories if current.lower() in c.lower()][:25]

async def shop_item_auto(interaction: discord.Interaction, current: str):
    items = []
    guild_id = str(interaction.guild_id)
    party = get_active_party(guild_id)
    
    for g_name, g_items in db["shop"].items():
        for i_id, i_data in g_items.items():
            if not is_item_locked(i_data, guild_id, party):
                items.append(i_data["name"])
    return [app_commands.Choice(name=i, value=i) for i in items if current.lower() in i.lower()][:25]

async def shop_target_auto(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild_id)
    party = get_active_party(guild_id)
    targets = ["Storage"]
    if guild_id in db["wallet"] and party in db["wallet"][guild_id].get("parties", {}):
        targets.extend(db["wallet"][guild_id]["parties"][party].get("members", []))
    return [app_commands.Choice(name=t, value=t) for t in targets if current.lower() in t.lower()][:25]

# --- PARTY COMMANDS ---

async def party_autocomplete(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild_id)
    if guild_id not in db["wallet"] or "parties" not in db["wallet"][guild_id]:
        return []
    parties = list(db["wallet"][guild_id]["parties"].keys())
    return [app_commands.Choice(name=p, value=p) for p in parties if current.lower() in p.lower()][:25]

@bot.tree.command(name="party", description="Manage the party, members, and currency")
@app_commands.describe(action="create/setactive/balance/add_funds/remove_funds/set_currency/add_member/remove_member/info", value="Amount, character, or currency name", party_name="Specific party (Defaults to Active)")
async def cmd_party(interaction: discord.Interaction, action: str, value: str = None, party_name: str = None):
    if interaction.user.id not in ADMIN_USER_IDS:
        return await interaction.response.send_message("âŒ You do not have permission to manage parties.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    action = action.lower()
    
    if action == "create":
        if not value: return await interaction.response.send_message("âŒ Provide a party name in 'value'.", ephemeral=True)
        init_party_if_missing(guild_id, value)
        return await interaction.response.send_message(f"âœ… Party **{value}** created!")
        
    if action == "setactive":
        if not value: return await interaction.response.send_message("âŒ Provide a party name in 'value'.", ephemeral=True)
        init_party_if_missing(guild_id, value)
        db["wallet"][guild_id]["active_party"] = value
        save_data("wallet", db["wallet"])
        return await interaction.response.send_message(f"âœ… Active party set to **{value}**.")
        
    target_party = party_name if party_name else get_active_party(guild_id)
    init_party_if_missing(guild_id, target_party)
    wallet = db["wallet"][guild_id]["parties"][target_party]
    
    if action in ["add_funds", "remove_funds", "set_currency", "add_member", "remove_member"]:
        if interaction.user.id not in ADMIN_USER_IDS:
            return await interaction.response.send_message("âŒ You do not have permission.", ephemeral=True)
            
    if action == "balance":
        await interaction.response.send_message(f"ðŸ’³ The **{target_party}** party has **{wallet['balance']} {wallet['currency_name']}**.")
    elif action == "info":
        members = ", ".join(wallet.get("members", [])) or "None"
        desc = f"**Currency:** {wallet['currency_name']}\n**Balance:** {wallet['balance']}\n**Members:** {members}"
        embed = discord.Embed(title=f"ðŸ›¡ï¸ Party: {target_party}", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
    elif action == "set_currency":
        if not value: return await interaction.response.send_message("âŒ Provide a currency name in 'value'.", ephemeral=True)
        wallet["currency_name"] = value
        save_data("wallet", db["wallet"])
        await interaction.response.send_message(f"ðŸ“ Currency for **{target_party}** set to **{value}**.")
    elif action == "add_funds":
        try: amount = int(value)
        except: return await interaction.response.send_message("âŒ Value must be a number.", ephemeral=True)
        wallet["balance"] += amount
        save_data("wallet", db["wallet"])
        await interaction.response.send_message(f"ðŸ’° Added {amount} {wallet['currency_name']} to **{target_party}**! New Balance: {wallet['balance']}")
    elif action == "remove_funds":
        try: amount = int(value)
        except: return await interaction.response.send_message("âŒ Value must be a number.", ephemeral=True)
        wallet["balance"] = max(0, wallet["balance"] - amount)
        save_data("wallet", db["wallet"])
        await interaction.response.send_message(f"ðŸ’¸ Removed {amount} {wallet['currency_name']} from **{target_party}**. New Balance: {wallet['balance']}")
    elif action == "add_member":
        if not value: return await interaction.response.send_message("âŒ Provide a character name in 'value'.", ephemeral=True)
        if "members" not in wallet: wallet["members"] = []
        if value not in wallet["members"]:
            wallet["members"].append(value)
            save_data("wallet", db["wallet"])
        await interaction.response.send_message(f"ðŸ‘¥ Added **{value}** to the **{target_party}** party.")
    elif action == "remove_member":
        if not value: return await interaction.response.send_message("âŒ Provide a character name in 'value'.", ephemeral=True)
        if "members" in wallet and value in wallet["members"]:
            wallet["members"].remove(value)
            save_data("wallet", db["wallet"])
            await interaction.response.send_message(f"ðŸ‘‹ Removed **{value}** from the **{target_party}** party.")
        else:
            await interaction.response.send_message("âŒ Member not found.", ephemeral=True)
    else:
        await interaction.response.send_message("âŒ Invalid action.", ephemeral=True)

# --- STORAGE COMMANDS ---
@bot.tree.command(name="storage", description="Open the unified Storage Dashboard")
@app_commands.describe(character="Target character", party_name="Specific party (Defaults to Active)", view_only="If True, just lists items.")
@app_commands.autocomplete(character=character_target_auto, party_name=party_autocomplete)
async def cmd_storage(interaction: discord.Interaction, character: str = None, party_name: str = None, view_only: bool = False):
    guild_id = str(interaction.guild_id)
    target_party = party_name if party_name else get_active_party(guild_id)
    init_party_if_missing(guild_id, target_party)
    
    if view_only:
        wallet = db["wallet"][guild_id]["parties"][target_party]
        storage = wallet.get("storage", {})
        if not storage:
            return await interaction.response.send_message(f"ðŸ“¦ The **{target_party}** storage is currently empty.")
            
        desc = ""
        for i_uid, data in storage.items():
            name = data.get("name", "Unknown")
            uses = data.get("uses", 1)
            if isinstance(uses, int):
                desc += f"â€¢ **{name}** ({uses} uses left)\n"
            else:
                desc += f"â€¢ **{name}** ({uses})\n"
                
        if len(desc) > 3500:
            desc = desc[:3500] + "\n...and more."
            
        embed = discord.Embed(title=f"ðŸ“¦ {target_party} Storage", description=desc, color=discord.Color.dark_grey())
        return await interaction.response.send_message(embed=embed)

    if character and not validate_target(interaction, character):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)
        
    char_name = character if character else get_active_name(interaction)
    if not char_name:
        return await interaction.response.send_message("âŒ You must have an active character.", ephemeral=True)
        
    view = StorageDashboardView(char_name, guild_id, target_party)
    uid, pdata = view.get_char_pdata()
    
    if not pdata:
        return await interaction.response.send_message(f"âŒ Character **{char_name}** not found.", ephemeral=True)
        
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

# --- SHOP COMMANDS ---
@bot.tree.command(name="shop", description="View the shop or buy an item")
@app_commands.describe(action="list/buy/lock/unlock", item_name="Item to buy", quantity="Amount to buy", target="Who gets the item (Character or Storage)", party_name="Which wallet to use (Defaults to Active)")
@app_commands.autocomplete(category=shop_category_auto, item_name=shop_item_auto, target=shop_target_auto)
async def cmd_shop(interaction: discord.Interaction, action: str, category: str = None, item_name: str = None, quantity: int = 1, target: str = None, party_name: str = None):
    if target and not validate_target(interaction, target):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)
    action = action.lower()
    guild_id = str(interaction.guild_id)
    target_party = party_name if party_name else get_active_party(guild_id)
    
    init_party_if_missing(guild_id, target_party)
    wallet = db["wallet"][guild_id]["parties"][target_party]
    currency = wallet["currency_name"]
    
    if action == "list":
        if not category or category not in db["shop"]:
            cats = ", ".join(db["shop"].keys())
            return await interaction.response.send_message(f"ðŸ›’ **Shop Categories:** {cats}\nUse `/shop list <category>` to view items.", ephemeral=True)
            
        items = db["shop"][category]
        lines = []
        for i_id, i_data in sorted(items.items(), key=lambda x: x[1]['name']):
            if is_item_locked(i_data, guild_id, target_party): continue
            lines.append(f"â€¢ **{i_data['name']}** - {i_data['price']} {currency}")
            
        if not lines: lines = ["No items available in this category."]
        desc = "\n".join(lines)
        if len(desc) > 4000: desc = desc[:4000] + "... (truncated)"
            
        embed = discord.Embed(title=f"ðŸ›’ Shop: {category} ({target_party} Party)", description=desc, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        
    elif action == "buy":
        if not item_name: return await interaction.response.send_message("âŒ Specify an item_name.", ephemeral=True)
        
        item_data = None
        for g, items in db["shop"].items():
            if item_name.lower() in items:
                item_data = items[item_name.lower()]
                break
                
        if not item_data: return await interaction.response.send_message(f"âŒ **{item_name}** not found in the shop.", ephemeral=True)
        if is_item_locked(item_data, guild_id, target_party):
            return await interaction.response.send_message(f"ðŸ”’ **{item_data['name']}** is out of stock for this party!", ephemeral=True)
            
        total_cost = item_data["price"] * quantity
        if wallet["balance"] < total_cost:
            return await interaction.response.send_message(f"âŒ The **{target_party}** party cannot afford this! Cost: **{total_cost} {currency}**, Balance: **{wallet['balance']} {currency}**.", ephemeral=True)
            
        char_name = target if target else get_active_name(interaction)
        group, key, base_data = get_item_base_data(item_data['name'])
        max_uses = parse_uses(base_data.get("uses", "1")) if base_data else 1
        
        if char_name.lower() == "storage":
            if "storage" not in wallet: wallet["storage"] = {}
            for _ in range(quantity):
                new_uid = generate_uid(item_data['name'])
                wallet["storage"][new_uid] = {
                    "name": item_data['name'],
                    "uses": max_uses,
                    "max_uses": max_uses,
                    "preference": "Neutral"
                }
            wallet["balance"] -= total_cost
            save_data("wallet", db["wallet"])
            await interaction.response.send_message(f"ðŸ›ï¸ Bought **{quantity}x {item_data['name']}** and sent to **Storage**!\nRemaining Balance: **{wallet['balance']} {currency}**")
        else:
            # Check if character is in the party
            members = wallet.get("members", [])
            if char_name not in members:
                return await interaction.response.send_message(f"âŒ **{char_name}** is not in the **{target_party}** party! Add them first using `/party add_member`.", ephemeral=True)
                
            success, msg = grant_item(char_name, item_data['name'], quantity, max_uses, "Neutral")
            if success:
                wallet["balance"] -= total_cost
                save_data("wallet", db["wallet"])
                await interaction.response.send_message(f"ðŸ›ï¸ Bought **{quantity}x {item_data['name']}** for **{char_name}**!\nRemaining Balance: **{wallet['balance']} {currency}**")
            else:
                await interaction.response.send_message(f"âŒ {msg}", ephemeral=True)
                
    elif action in ["lock", "unlock"]:
        if interaction.user.id not in ADMIN_USER_IDS:
            return await interaction.response.send_message("âŒ You do not have permission.", ephemeral=True)
        if not item_name: return await interaction.response.send_message("âŒ Specify an item_name.", ephemeral=True)
        
        item_found = False
        for g, items in db["shop"].items():
            if item_name.lower() in items:
                if "lock_overrides" not in wallet: wallet["lock_overrides"] = {}
                wallet["lock_overrides"][item_name.lower()] = (action == "lock")
                item_found = True
                break
                
        if item_found:
            save_data("wallet", db["wallet"])
            await interaction.response.send_message(f"âœ… **{item_name}** has been **{action}ed** for **{target_party}**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"âŒ **{item_name}** not found in the shop.", ephemeral=True)


# --- UPGRADE COMMANDS ---
@bot.tree.command(name="upgrade", description="Manage Crystal Hearts and Dimensional Satchels")
@app_commands.describe(action="satchel/heart/set_max_hearts", target="Character or Party", amount="Amount or True/False")
@app_commands.autocomplete(target=char_item_auto) # Use char auto (Wait, char_item_auto doesn't fit 'party')
async def cmd_upgrade(interaction: discord.Interaction, action: str, target: str, amount: str):
    if interaction.user.id not in ADMIN_USER_IDS:
        return await interaction.response.send_message("âŒ You do not have permission.", ephemeral=True)
        
    action = action.lower()
    guild_id = str(interaction.guild_id)
    
    if action == "set_max_hearts":
        try:
            val = int(amount)
        except ValueError:
            return await interaction.response.send_message("âŒ Amount must be an integer.", ephemeral=True)
            
        if guild_id not in db["wallet"] or target not in db["wallet"][guild_id].get("parties", {}):
            return await interaction.response.send_message(f"âŒ Party **{target}** not found.", ephemeral=True)
            
        db["wallet"][guild_id]["parties"][target]["max_hearts"] = val
        save_data("wallet", db["wallet"])
        return await interaction.response.send_message(f"â¤ï¸ Max Crystal Hearts for **{target}** set to **{val}**.")
        
    # For satchel/heart, we need a character
    char_name = target
    char_pdata = None
    char_stats = None
    for uid, pdata in db["players"].items():
        if "characters" in pdata and char_name in pdata["characters"]:
            char_pdata = pdata
            char_stats = pdata["characters"][char_name].setdefault("stats", {})
            break
            
    if not char_stats:
        return await interaction.response.send_message(f"âŒ Character **{char_name}** not found.", ephemeral=True)
        
    if action == "satchel":
        val = amount.lower() in ["true", "1", "yes"]
        char_stats["dimensional_satchel"] = val
        save_data("players", db["players"])
        status = "Granted" if val else "Removed"
        return await interaction.response.send_message(f"ðŸŽ’ Dimensional Satchel **{status}** for **{char_name}**! Their inventory limit is now {'20' if val else '16'}.")
        
    elif action == "heart":
        try:
            val = int(amount)
        except ValueError:
            return await interaction.response.send_message("âŒ Amount must be an integer.", ephemeral=True)
            
        current = char_stats.get("crystal_hearts", 0)
        
        if val > 0:
            # Check party max hearts
            max_hearts = 3
            if guild_id in db.get("wallet", {}):
                for p_name, p_data in db["wallet"][guild_id].get("parties", {}).items():
                    if char_name in p_data.get("members", []):
                        max_hearts = p_data.get("max_hearts", 3)
                        break
                        
            if current + val > max_hearts:
                return await interaction.response.send_message(f"âŒ This would exceed the party's Crystal Heart cap ({current}/{max_hearts})!", ephemeral=True)
                
        char_stats["crystal_hearts"] = current + val
        char_stats["max_hp"] = char_stats.get("max_hp", 100) + (20 * val)
        char_stats["current_hp"] = char_stats.get("current_hp", 100) + (20 * val)
        
        # Ensure current_hp doesn't exceed max_hp if healed past max, but since we add to both, it's fine.
        # Wait, if we remove hearts, current_hp might exceed max_hp, cap it.
        if char_stats["current_hp"] > char_stats["max_hp"]:
            char_stats["current_hp"] = char_stats["max_hp"]
            
        save_data("players", db["players"])
        
        verb = "Added" if val > 0 else "Removed"
        return await interaction.response.send_message(f"â¤ï¸ **{verb} {abs(val)}x Crystal Hearts** for **{char_name}**!\nMax HP and Current HP modified by **{val * 20}**.")
    else:
        return await interaction.response.send_message("âŒ Invalid action.", ephemeral=True)



@bot.tree.command(name="editpreference", description="Edit your character's item preferences")
@app_commands.autocomplete(itemname=global_item_auto, target=target_auto)
@app_commands.describe(itemname="The ITEM you want to set a preference for", preference="The preference tier", target="Leave blank to use active character")
@app_commands.choices(preference=[
    app_commands.Choice(name="Obsessed", value="Obsessed"),
    app_commands.Choice(name="Well-Liked", value="Well-Liked"),
    app_commands.Choice(name="Disliked", value="Disliked"),
    app_commands.Choice(name="Allergic", value="Allergic"),
    app_commands.Choice(name="Neutral (Remove)", value="Neutral")
])
async def cmd_editpreference(interaction: discord.Interaction, itemname: str, preference: str, target: str = None):
    if target and not validate_target(interaction, target):
        return await interaction.response.send_message("âŒ Target out of scope.", ephemeral=True)
    uid = f"{interaction.user.id}_{interaction.guild_id}"
    if uid not in db["players"]:
        return await interaction.response.send_message("âŒ You are not registered.", ephemeral=True)
        
    char_name = target if target else get_active_name(interaction)
    if not char_name or char_name not in db["players"][uid].get("characters", {}):
        return await interaction.response.send_message("âŒ Character not found. Set an active character or specify a valid target.", ephemeral=True)
        
    char_data = db["players"][uid]["characters"][char_name]
    if "preferences" not in char_data:
        char_data["preferences"] = {}
        
    if preference == "Neutral":
        if itemname in char_data["preferences"]:
            del char_data["preferences"][itemname]
        msg = f"âœ… Removed **{itemname}** from **{char_name}**'s preferences (Set to Neutral)."
    else:
        char_data["preferences"][itemname] = preference
        msg = f"âœ… Set **{char_name}**'s preference for **{itemname}** to **{preference}**."
        
    save_data("players", db["players"])
    await interaction.response.send_message(msg)




@bot.tree.command(name="removemagic", description="Remove a MAGIC from your character")
@app_commands.describe(target="Specific character (Defaults to Active)", magic_name="The exact name of the magic to remove")
@app_commands.autocomplete(target=target_auto, magic_name=magic_name_auto)
async def cmd_removemagic(interaction: discord.Interaction, magic_name: str, target: str = None):
    char_name = target if target else get_active_name(interaction)
    if not can_edit(interaction, char_name):
        return await interaction.response.send_message("âŒ You do not have permission to edit this character.", ephemeral=True)
        
    owner_id = None
    for p_uid, pdata in db["players"].items():
        if "characters" in pdata and char_name in pdata["characters"]:
            owner_id = p_uid
            break
            
    if not owner_id: return await interaction.response.send_message("âŒ Character not found.", ephemeral=True)
    
    char_data = db["players"][owner_id]["characters"][char_name]
    if "magic" not in char_data or magic_name not in char_data["magic"]:
        return await interaction.response.send_message(f"âŒ Could not find MAGIC **{magic_name}**.", ephemeral=True)
        
    del char_data["magic"][magic_name]
    save_data("players", db["players"])
    await interaction.response.send_message(f"âœ… Removed MAGIC **{magic_name}** from **{char_name}**.", ephemeral=True)

@bot.tree.command(name="dmtargetscope", description="[DM ONLY] Change your targeting scope")
@app_commands.choices(scope=[
    app_commands.Choice(name="Global", value="global"),
    app_commands.Choice(name="Party", value="party"),
    app_commands.Choice(name="Own", value="own")
])
async def cmd_dmtargetscope(interaction: discord.Interaction, scope: str):
    uid = str(interaction.user.id)
    if interaction.user.id not in ADMIN_USER_IDS:
        return await interaction.response.send_message("âŒ This command is restricted to DMs.", ephemeral=True)
    
    if "dms" not in db:
        db["dms"] = {}
    if uid not in db["dms"]:
        db["dms"][uid] = {}
        
    db["dms"][uid]["target_scope"] = scope
    save_data("dms", db["dms"])
    await interaction.response.send_message(f"âœ… Targeting scope set to **{scope.capitalize()}**.", ephemeral=True)


@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands globally!")
    except Exception as e:
        await ctx.send(f"Error syncing: {e}")

@bot.command()
@commands.is_owner()
async def sync_guild(ctx):
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} commands specifically to this guild for instant access!")
    except Exception as e:
        await ctx.send(f"Error syncing: {e}")


# --- METRONOME COMMANDS ---
class MetronomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Reroll ðŸŽ²", style=discord.ButtonStyle.primary, custom_id="btn_metronome_reroll")
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        import random
        metronomes = list(db.get("metronomes", {}).values())
        if not metronomes:
            return await interaction.response.send_message("âŒ Metronome database is empty.", ephemeral=True)
            
        chosen = random.choice(metronomes)
        
        embed = discord.Embed(title=f"ðŸŽ² Metronome: {chosen['name']}", color=discord.Color.brand_green())
        
        hit_text = chosen['hit']
        if chosen.get('tags'):
            hit_text = f"{hit_text}, {chosen['tags']}"
            
        embed.add_field(name="HIT", value=hit_text, inline=False)
        embed.add_field(name="Damage", value=chosen['damage'], inline=False)
        embed.add_field(name="Effect", value=chosen['effect'], inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="metronome", description="Roll a random metronome, or lookup a specific one")
@app_commands.describe(name="Leave blank to roll randomly, or type a name to lookup")
@app_commands.autocomplete(name=metronome_auto)
async def cmd_metronome(interaction: discord.Interaction, name: str = None):
    import random
    metronomes = db.get("metronomes", {})
    if not metronomes:
        return await interaction.response.send_message("âŒ Metronome database is empty.", ephemeral=True)
        
    if name:
        chosen = metronomes.get(name)
        if not chosen:
            return await interaction.response.send_message(f"âŒ Metronome **{name}** not found.", ephemeral=True)
        view = None
    else:
        chosen = random.choice(list(metronomes.values()))
        view = MetronomeView()
        
    embed = discord.Embed(title=f"ðŸŽ² Metronome: {chosen['name']}", color=discord.Color.brand_green())
    
    hit_text = chosen['hit']
    if chosen.get('tags'):
        hit_text = f"{hit_text}, {chosen['tags']}"
        
    embed.add_field(name="HIT", value=hit_text, inline=False)
    embed.add_field(name="Damage", value=chosen['damage'], inline=False)
    embed.add_field(name="Effect", value=chosen['effect'], inline=False)
    
    if view:
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed)

@bot.command()
@commands.is_owner()
async def clearguild(ctx):
    try:
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        await ctx.send("ðŸ§¹ Cleared all ghost guild-specific slash commands! Restart your Discord app (Ctrl+R) and it will now fall back to the global commands.")
    except Exception as e:
        await ctx.send(f"Error: {e}")
        
@bot.command()
@commands.is_owner()
async def clearglobal(ctx):
    try:
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        await ctx.send("ðŸ§¹ Cleared all global slash commands!")
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.tree.command(name="joinparty", description="Join a party with one of your characters")
@app_commands.describe(char_name="The character to add", party_name="The party to join")
@app_commands.autocomplete(char_name=character_auto, party_name=party_autocomplete)
async def cmd_joinparty(interaction: discord.Interaction, char_name: str, party_name: str):
    player_key = f"{interaction.user.id}_{interaction.guild_id}"
    guild_id = str(interaction.guild_id)
    db_players = db["players"]
    
    if player_key not in db_players or char_name not in db_players[player_key].get("characters", {}):
        return await interaction.response.send_message(f"âŒ You don't own a character named **{char_name}**.", ephemeral=True)
        
    db_wallet = db["wallet"]
    if guild_id not in db_wallet or "parties" not in db_wallet[guild_id]:
        return await interaction.response.send_message("âŒ No parties exist in this server yet.", ephemeral=True)
        
    if party_name not in db_wallet[guild_id]["parties"]:
        return await interaction.response.send_message(f"âŒ The party **{party_name}** does not exist.", ephemeral=True)
        
    party = db_wallet[guild_id]["parties"][party_name]
    members = party.setdefault("members", [])
    
    if char_name in members:
        return await interaction.response.send_message(f"âš ï¸ **{char_name}** is already in the **{party_name}** party!", ephemeral=True)
        
    members.append(char_name)
    save_data("wallet", db_wallet)
    await interaction.response.send_message(f"ðŸŽ‰ **{char_name}** has joined the **{party_name}** party!")

@bot.tree.command(name="leaveparty", description="Leave your current party with one of your characters")
@app_commands.describe(char_name="The character to remove from their party")
@app_commands.autocomplete(char_name=character_auto)
async def cmd_leaveparty(interaction: discord.Interaction, char_name: str):
    player_key = f"{interaction.user.id}_{interaction.guild_id}"
    guild_id = str(interaction.guild_id)
    db_players = db["players"]
    
    if player_key not in db_players or char_name not in db_players[player_key].get("characters", {}):
        return await interaction.response.send_message(f"âŒ You don't own a character named **{char_name}**.", ephemeral=True)
        
    db_wallet = db["wallet"]
    if guild_id not in db_wallet or "parties" not in db_wallet[guild_id]:
        return await interaction.response.send_message("âŒ No parties exist in this server yet.", ephemeral=True)
        
    left_parties = []
    for p_name, party in db_wallet[guild_id]["parties"].items():
        members = party.get("members", [])
        if char_name in members:
            members.remove(char_name)
            left_parties.append(p_name)
            
    if not left_parties:
        return await interaction.response.send_message(f"âš ï¸ **{char_name}** is not in any party.", ephemeral=True)
        
    save_data("wallet", db_wallet)
    await interaction.response.send_message(f"ðŸ‘‹ **{char_name}** has left the following parties: **{', '.join(left_parties)}**")



class CharacterListGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="characterlist", description="List characters")
        
    @app_commands.command(name="party", description="List all characters in a party")
    @app_commands.autocomplete(party_name=party_autocomplete)
    async def list_party(self, interaction: discord.Interaction, party_name: str = None):
        guild_id = str(interaction.guild_id)
        target_party = party_name if party_name else get_active_party(guild_id)
        init_party_if_missing(guild_id, target_party)
        
        wallet = db["wallet"][guild_id]["parties"][target_party]
        members = wallet.get("members", [])
        
        if not members:
            return await interaction.response.send_message(f"ðŸ›¡ï¸ The **{target_party}** party has no members.")
            
        desc = "\n".join([f"â€¢ {m}" for m in members])
        embed = discord.Embed(title=f"ðŸ›¡ï¸ Members of {target_party}", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        
    @app_commands.command(name="player", description="List all characters owned by a player in this server")
    async def list_player(self, interaction: discord.Interaction, target_user: discord.Member = None):
        user = target_user if target_user else interaction.user
        player_key = f"{user.id}_{interaction.guild_id}"
        
        db_players = db["players"]
        if player_key not in db_players or not db_players[player_key].get("roster"):
            return await interaction.response.send_message(f"âŒ **{user.display_name}** has no characters registered in this server.")
            
        roster = db_players[player_key]["roster"]
        active = db_players[player_key].get("active")
        
        desc = "\n".join([f"â€¢ {c} {'*(Active)*' if c == active else ''}" for c in roster])
        embed = discord.Embed(title=f"ðŸ‘¤ {user.display_name}'s Characters", description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed)


bot.tree.add_command(CharacterListGroup())


class ConfirmClearView(discord.ui.View):
    def __init__(self, target_type: str, target_name: str, guild_id: str):
        super().__init__()
        self.target_type = target_type
        self.target_name = target_name
        self.guild_id = guild_id

    @discord.ui.button(label="Confirm Clear", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target_type == "target":
            for p_uid, pdata in db["players"].items():
                if p_uid.endswith(f"_{self.guild_id}") and "characters" in pdata and self.target_name in pdata["characters"]:
                    pdata["characters"][self.target_name]["inventory"] = {}
                    save_data("players", db["players"])
                    for child in self.children: child.disabled = True
                    return await interaction.response.edit_message(content=f"âœ… Cleared the inventory of **{self.target_name}**.", view=self)
            return await interaction.response.edit_message(content=f"âŒ Could not find target **{self.target_name}**.")
            
        elif self.target_type == "party":
            party = db["wallet"].get(self.guild_id, {}).get("parties", {}).get(self.target_name)
            if not party: return await interaction.response.edit_message(content=f"âŒ Party **{self.target_name}** not found.")
            members = party.get("members", [])
            for m in members:
                for p_uid, pdata in db["players"].items():
                    if p_uid.endswith(f"_{self.guild_id}") and "characters" in pdata and m in pdata["characters"]:
                        pdata["characters"][m]["inventory"] = {}
            save_data("players", db["players"])
            for child in self.children: child.disabled = True
            return await interaction.response.edit_message(content=f"âœ… Cleared local inventories for all members of party **{self.target_name}**.", view=self)
            
        elif self.target_type == "storage":
            party = db["wallet"].get(self.guild_id, {}).get("parties", {}).get(self.target_name)
            if not party: return await interaction.response.edit_message(content=f"âŒ Party **{self.target_name}** not found.")
            party["storage"] = {}
            save_data("wallet", db["wallet"])
            for child in self.children: child.disabled = True
            return await interaction.response.edit_message(content=f"âœ… Cleared shared storage inventory for party **{self.target_name}**.", view=self)

@bot.tree.command(name="clearinventory", description="DM ONLY: Clear a character, party, or storage inventory")
@app_commands.describe(target="Clear a specific character's inventory", party="Clear all party members' inventories", storage="Clear a party's shared storage")
@app_commands.autocomplete(target=target_auto, party=party_autocomplete, storage=party_autocomplete)
async def cmd_clearinventory(interaction: discord.Interaction, target: str = None, party: str = None, storage: str = None):
    if interaction.user.id not in ADMIN_USER_IDS:
        return await interaction.response.send_message("âŒ Denied.", ephemeral=True)
        
    if not any([target, party, storage]):
        return await interaction.response.send_message("âŒ You must specify one of: target, party, or storage.", ephemeral=True)
        
    if sum(bool(x) for x in [target, party, storage]) > 1:
        return await interaction.response.send_message("âŒ Please only specify ONE modifier per command.", ephemeral=True)
        
    guild_id = str(interaction.guild_id)
    if target:
        view = ConfirmClearView("target", target, guild_id)
        msg = f"âš ï¸ Are you sure you want to completely wipe the personal inventory of **{target}**?"
    elif party:
        view = ConfirmClearView("party", party, guild_id)
        msg = f"âš ï¸ Are you sure you want to completely wipe the personal inventories of ALL members in the **{party}** party?"
    elif storage:
        view = ConfirmClearView("storage", storage, guild_id)
        msg = f"âš ï¸ Are you sure you want to completely wipe the external shared storage of the **{storage}** party?"
        
    await interaction.response.send_message(msg, view=view, ephemeral=True)


bot.run(TOKEN)

