import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import time
import os

# ---------------- CONFIG ----------------
# DISCORD_TOKEN should be set in Replit Secrets / Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable")


# 🔴 EDIT STAFF ROLES HERE (role names in your server)
STAFF_ROLES = ["👑- Godfather", "Father"]

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
        print(f"🤖 Logged in as {bot.user}")
    except Exception as e:
        print(f"❌ Sync Error: {e}")


# ---------------- STAFF CHECK ----------------
# Allow staff if they are:
# - server owner
# - Administrator
# - Manage Roles
# (We keep STAFF_ROLES as an optional fallback.)
def has_role_permissions(member: discord.Member) -> bool:
    if member.guild.owner_id == member.id:
        return True

    perms = getattr(member, "guild_permissions", None)
    if perms is None:
        return False

    if perms.administrator or perms.manage_roles:
        return True

    return any(role.name in STAFF_ROLES for role in member.roles)



# ---------------- ROLE SELECT ----------------
class RoleSelect(discord.ui.Select):
    def __init__(self, member, ingame_name):
        self.member = member
        self.ingame_name = ingame_name

        # Applicant role dropdown should show roles like "@RoleName".
        # (Discord displays role names; prefixing with @ isn't necessary.)
        # Keep same filter as before: show only usable roles.
        roles = [
            r for r in member.guild.roles
            if not r.managed
            and r != member.guild.default_role
        ]

        roles = [r for r in roles if r.name not in STAFF_ROLES][-25:]

        options = [
            discord.SelectOption(label=f"@{role.name}", value=str(role.id))
            for role in reversed(roles)
        ]


        super().__init__(
            placeholder="Select role for applicant...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))

        # If the bot can't change nicknames, don't break the interaction.
        try:
            await self.member.edit(nick=self.ingame_name)
        except Exception as e:
            print(f"Nickname Error: {e}")


        try:
            await self.member.add_roles(role)
        except Exception as e:
            print(f"Role Error: {e}")

        embeds = interaction.message.embeds
        if embeds:
            embed = embeds[0]
            embed.color = discord.Color.green()

            embed.set_field_at(
                4,
                name="Status",
                value=f"✅ Approved by {interaction.user.mention}",
                inline=False
            )

            embed.set_field_at(
                5,
                name="Progress",
                value="● ● ● Approved",
                inline=False
            )

            # ---------------- EDITED MESSAGE ----------------
            await interaction.message.edit(embed=embed, view=None)
        else:
            # No embed to update
            pass

        await interaction.response.send_message(
            f"✅ {self.member.mention} approved with {role.mention}",
            ephemeral=True
        )


class RoleView(discord.ui.View):
    def __init__(self, member, ingame_name):
        super().__init__(timeout=120)
        self.add_item(RoleSelect(member, ingame_name))


# ---------------- STAFF BUTTONS ----------------
class StaffButtons(discord.ui.View):
    def __init__(self, applicant_id, ingame_name):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.ingame_name = ingame_name

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.blurple)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_role_permissions(interaction.user):
            return await interaction.response.send_message("❌ No permission to manage roles.", ephemeral=True)

        member = interaction.guild.get_member(self.applicant_id)
        if member is None:
            member = await interaction.guild.fetch_member(self.applicant_id)

        view = RoleView(member, self.ingame_name)

        # Edit the original message so the buttons exist on the applicant embed.
        # (This also allows RoleSelect.callback to later remove them with view=None.)
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed is not None:
            embed.color = discord.Color.dark_gray()

        # Add a text list of assignable roles into the embed ("message format")
        if interaction.message.embeds:
            embed_for_roles = interaction.message.embeds[0]

            allowed_roles = [
                r for r in interaction.guild.roles
                if not r.managed
                and r != interaction.guild.default_role
                and r.name not in STAFF_ROLES
            ]

            # keep it readable in embed
            allowed_roles = allowed_roles[:25]
            roles_text = "\n".join([f"• {r.name}" for r in allowed_roles]) if allowed_roles else "None"

            # do not add "Roles Available" field to the embed

            await interaction.message.edit(embed=embed_for_roles, view=view)
        else:
            await interaction.message.edit(view=view)


        await interaction.response.send_message(
            "Role selection updated.",
            ephemeral=True
        )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not has_role_permissions(interaction.user):
            return await interaction.response.send_message("❌ No permission to manage roles.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()

        embed.set_field_at(
            4,
            name="Status",
            value=f"❌ Denied by {interaction.user.mention}",
            inline=False
        )

        embed.set_field_at(
            5,
            name="Progress",
            value="● ● ✖ Denied",
            inline=False
        )

        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message("❌ Application denied.", ephemeral=True)


# ---------------- VOUCH VIEW ----------------
class VouchView(discord.ui.View):
    def __init__(self, vouched_by, applicant_id, ingame_name):
        super().__init__(timeout=None)

        self.vouched_by = vouched_by
        self.applicant_id = applicant_id
        self.ingame_name = ingame_name

    @discord.ui.button(label="Accept Vouch", style=discord.ButtonStyle.green)
    async def accept_vouch(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.vouched_by:
            return await interaction.response.send_message("❌ Only vouched user.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.orange()

        embed.set_field_at(
            4,
            name="Status",
            value=f"✅ Vouched by {interaction.user.mention}",
            inline=False
        )

        embed.set_field_at(
            5,
            name="Progress",
            value="● ● ○ Vouch accepted",
            inline=False
        )

        staff_view = StaffButtons(self.applicant_id, self.ingame_name)

        await interaction.message.edit(embed=embed, view=staff_view)

        await interaction.response.send_message("✅ Vouch accepted.", ephemeral=True)

    @discord.ui.button(label="Deny Vouch", style=discord.ButtonStyle.gray)
    async def deny_vouch(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.vouched_by:
            return await interaction.response.send_message("❌ Only vouched user.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()

        embed.set_field_at(
            4,
            name="Status",
            value=f"❌ Vouch denied by {interaction.user.mention}",
            inline=False
        )

        embed.set_field_at(
            5,
            name="Progress",
            value="● ✖ Vouch denied",
            inline=False
        )

        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message("❌ Vouch denied.", ephemeral=True)


# ---------------- WHITELIST BY MESSAGE (NO /whitelist) ----------------
REQ_CHANNEL_IDS = {
    1469276331672862862,1472233895654195284
}



def _parse_application_fields(text: str) -> tuple[str | None, str | None]:
    """Parse message format.

    Supports both:
    1) Multi-line:
       Full Name:\n<value>\nVouch:\n<id>

    2) Inline (as in your debug):
       Full Name:<value>\nVouch:<id>
    """
    # Normalize: remove blank lines, trim.
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    full_name = None
    vouch_raw = None

    for line in lines:
        if line.startswith("Full Name:"):
            # Full Name: tert  OR  Full Name:\ntert (handled by multi-line below)
            rest = line[len("Full Name:"):].strip()
            if rest:
                full_name = rest
        elif line.startswith("Vouch:"):
            rest = line[len("Vouch:"):].strip()
            if rest:
                vouch_raw = rest

    # Multi-line fallback: if value is on the next line
    if full_name is None or vouch_raw is None:
        i = 0
        while i < len(lines):
            if full_name is None and lines[i] == "Full Name:" and (i + 1) < len(lines):
                full_name = lines[i + 1]
                i += 2
                continue
            if vouch_raw is None and lines[i] == "Vouch:" and (i + 1) < len(lines):
                vouch_raw = lines[i + 1]
                i += 2
                continue
            i += 1

    return full_name, vouch_raw




@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    if message.guild is None:
        return

    if message.channel.id not in REQ_CHANNEL_IDS:
        return


    # Debug logs so you can see why it doesn't trigger
    print(f"[REQ] message from {message.author} ({message.author.id}) in #{message.channel}:")
    print(message.content)

    full_name, vouch_raw = _parse_application_fields(message.content)

    if not full_name or not vouch_raw:
        print(f"[REQ] parse failed full_name={full_name!r}, vouch_raw={vouch_raw!r}")
        return


    # No Role line anymore; use Full Name as the in-game name.
    ingame_name = full_name


    # Vouch can be a mention (<@id>) or a username/nickname.
    # Try mention/id first, then fall back to name match.
    vouched_member = None

    # Mention form: <@123...>
    if vouch_raw.startswith("<@") and vouch_raw.endswith(">"):
        vouch_clean = vouch_raw.replace("<@", "").replace(">", "").replace("!", "").strip()
        try:
            vouched_by_id = int(vouch_clean)
            vouched_member = message.guild.get_member(vouched_by_id) or await message.guild.fetch_member(vouched_by_id)
        except Exception:
            vouched_member = None

    # If it's not mention/id, treat as name (username or nickname)
    if vouched_member is None:
        search = vouch_raw.lower()
        try:
            members = message.guild.members
            if not members:
                members = await message.guild.fetch_members(limit=None)
        except Exception:
            return

        for m in members:
            if m.display_name.lower() == search or m.name.lower() == search:
                vouched_member = m
                break

    if vouched_member is None:
        return


    applicant = message.author

    joined = applicant.joined_at
    if joined:
        delta = datetime.now(timezone.utc) - joined
        joined_text = f"{delta.days} days ago" if delta.days < 30 else f"{delta.days // 30} month ago"
    else:
        joined_text = "Unknown"

    embed = discord.Embed(
        title="Whitelist Application",
        color=discord.Color.dark_gray(),
        timestamp=datetime.now()
    )

    embed.set_author(name=applicant.name, icon_url=applicant.display_avatar.url)

    embed.add_field(name="Applicant", value=applicant.mention, inline=True)
    embed.add_field(name="In-game Name", value=ingame_name, inline=True)
    embed.add_field(name="Vouched By", value=vouched_member.mention, inline=True)
    embed.add_field(name="Joined Server", value=joined_text, inline=True)

    embed.add_field(name="Status", value=f"Waiting for {vouched_member.mention}", inline=False)
    embed.add_field(name="Progress", value="● ○ ○ Waiting for vouch", inline=False)

    embed.set_footer(text=f"{message.guild.name}")

    image_filename = "standard (1).gif"
    file = discord.File(image_filename, filename=image_filename)
    embed.set_image(url=f"attachment://{image_filename}")

    view = VouchView(vouched_member.id, applicant.id, ingame_name)

    await message.delete()
    await message.channel.send(embed=embed, view=view, file=file)




# ---------------- RUN ----------------
bot.run(TOKEN)

