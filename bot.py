    import os
import json
import time
import datetime
from datetime import timedelta
from collections import defaultdict, deque

import asyncio
import pytz
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands
from discord.ui import View, button
import pytesseract
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
from PIL import Image
import io
import re
import platform

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"


GUILD_ID = 1307397558787899515  # Define GUILD_ID at the top!
ANNOUNCEMENT_CHANNEL_ID = 1309364152690675803 # 🛠️ Replace with your actual channel ID
MOD_LOG_CHANNEL_ID = 1361455371654398015  # replace with your actual mod-log channel ID



TEAM_NAMES = [
    "Washington", "Tennessee", "Seattle", "San Francisco", "San Diego",
    "Pittsburgh", "Philadelphia", "New York", "New Orleans", "New England",
    "Newark", "Minnesota", "Miami", "Los Angeles", "Las Vegas", "Kansas City",
    "Jacksonville", "Indianapolis", "Houston", "Green Bay", "Detroit",
    "Denver", "Dallas", "Cleveland", "Cincinnati", "Chicago", "Charlotte",
    "Buffalo", "Baltimore", "Atlanta", "Arizona", "Tampa Bay"
]

def get_user_team(user: discord.Member):
    for role in user.roles:
        if role.name in TEAM_NAMES:
            return role.name
    return None

# 👇 Add this here
async def alert_fo_of_gm_action(guild: discord.Guild, acting_member: discord.Member, action: str, target: discord.Member):
    gm_role = discord.utils.get(guild.roles, name="General Manager")
    fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
    
    if not gm_role or not fo_role:
        return

    if gm_role not in acting_member.roles:
        return

    team_name = None
    for role in acting_member.roles:
        if role.name in TEAM_NAMES:
            team_name = role.name
            break

    if not team_name:
        return

    franchise_owner = None
    for member in fo_role.members:
        if any(role.name == team_name for role in member.roles):
            franchise_owner = member
            break

    if not franchise_owner or franchise_owner == acting_member:
        return

    try:
        embed = discord.Embed(
            title="UFFL - GM Action Alert",
            description=f"Your GM **{acting_member.display_name}** has **{action}** **{target.display_name}**.",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Team: {team_name}")
        await franchise_owner.send(embed=embed)
    except discord.Forbidden:
        print(f"❌ Could not DM Franchise Owner {franchise_owner.display_name}")


class OfferView(View):
    def __init__(self, coach: discord.Member, team_name: str, guild: discord.Guild, *, timeout=86400):
        super().__init__(timeout=timeout)
        self.coach = coach
        self.team_name = team_name
        self.guild = guild

    @button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = self.guild
        member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
        if not member:
            await interaction.followup.send("❌ Could not find you in the server.", ephemeral=True)
            return

        team_role = discord.utils.get(guild.roles, name=self.team_name)
        free_agents_role = discord.utils.get(guild.roles, name="Free agents")

        if team_role:
            await member.add_roles(team_role)
        if free_agents_role and free_agents_role in member.roles:
            await member.remove_roles(free_agents_role)

        await interaction.followup.send(
            f"You have accepted the offer and joined **{self.team_name}**!",
            ephemeral=True
        )

        embed = discord.Embed(
            title="🏈 UFFL - Offer Accepted",
            description=f"{member.display_name} has accepted your offer to join **{self.team_name}**.",
            color=discord.Color.green()
        )
        await self.coach.send(embed=embed)
        self.stop()

    @button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You have declined the offer.", ephemeral=True)
        self.stop()


class DemandConfirmView(View):
    def __init__(self, user: discord.Member, team_name: str, guild: discord.Guild):
        super().__init__(timeout=60)
        self.user = user
        self.team_name = team_name
        self.guild = guild

    @button(label="Yes, demand", style=discord.ButtonStyle.danger)
    async def confirm_demand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = self.guild
        member = await guild.fetch_member(interaction.user.id)
        team_role = discord.utils.get(guild.roles, name=self.team_name)
        free_agents_role = discord.utils.get(guild.roles, name="Free agents")

        if team_role in member.roles:
            await member.remove_roles(team_role)
        if free_agents_role:
            await member.add_roles(free_agents_role)

        # Notify FO and GM
        fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
        gm_role = discord.utils.get(guild.roles, name="General Manager")

        fgm = []
        if fo_role:
            fgm += [m for m in fo_role.members if team_role in m.roles]
        if gm_role:
            fgm += [m for m in gm_role.members if team_role in m.roles]

        embed = discord.Embed(
            title="UFFL - Demand Alert",
            description=f"{member.mention} has demanded a release from **{self.team_name}**.",
            color=discord.Color.orange()
        )
        for person in fgm:
            try:
                await person.send(embed=embed)
            except discord.Forbidden:
                print(f"❌ Could not DM {person.display_name}")

        await interaction.followup.send(
            f"You have officially demanded from **{self.team_name}**. You're now a free agent.",
            ephemeral=True
        )
        self.stop()


    @button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Demand canceled.", ephemeral=True)
        self.stop()

class FootballFusionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        try:
            print("🧨 Force-wiping ALL GLOBAL AND GUILD COMMANDS...")

            # Clear and re-sync global commands
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            # Clear and re-sync guild commands
            guild = discord.Object(id=GUILD_ID)
            self.tree.clear_commands(guild=guild)

            # ✅ Register each command manually
            self.tree.add_command(ping, guild=guild)
            self.tree.add_command(offer, guild=guild)
            self.tree.add_command(release, guild=guild)
            self.tree.add_command(demand, guild=guild)
            self.tree.add_command(promote, guild=guild)
            self.tree.add_command(demote, guild=guild)
            self.tree.add_command(roster, guild=guild)
            self.tree.add_command(deadline_reminder, guild=guild)
            self.tree.add_command(game_thread, guild=guild)
            self.tree.add_command(add_to_thread, guild=guild)
            self.tree.add_command(close_thread, guild=guild)
            self.tree.add_command(disband, guild=guild)
            self.tree.add_command(gametime, guild=guild)
            self.tree.add_command(give_role, guild=guild)
            self.tree.add_command(submit_score, guild=guild)
            self.tree.add_command(delete_score, guild=guild)
            self.tree.add_command(view_scores, guild=guild)
            self.tree.add_command(team_info, guild=guild)
            self.tree.add_command(leaderboard, guild=guild)
            self.tree.add_command(group_create, guild=guild)
            self.tree.add_command(group_reset, guild=guild)
            self.tree.add_command(group_info, guild=guild)
            self.tree.add_command(group_thread, guild=guild)
            self.tree.add_command(fo_dashboard, guild=guild)
            self.tree.add_command(team_dashboard, guild=guild)
            self.tree.add_command(submit_stats, guild=guild)
            self.tree.add_command(stats_lb, guild=guild)
            self.tree.add_command(Import_Stats, guild=guild)
            self.tree.add_command(debugcheck, guild=guild)
            self.tree.add_command(botcmds, guild=guild)
            await self.tree.sync(guild=guild)

            # Debug output
            print("✅ All global and guild commands wiped and re-synced.")
            global_cmds = await self.tree.fetch_commands()
            guild_cmds = await self.tree.fetch_commands(guild=guild)
            print("🌐 Global commands:", [cmd.name for cmd in global_cmds])
            print("🏠 Guild commands:", [cmd.name for cmd in guild_cmds])

        except Exception as e:
            print(f"❌ setup_hook error: {e}")
            raise e


# ✅ Instantiate bot
bot = FootballFusionBot()


# ✅ Add ping as a test command
@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!", ephemeral=True)

print("✅ Ping command loaded")


# ✅ Error logging
@bot.event
async def on_application_command_error(interaction, error):
    print(f"Command error: {error}")


@bot.tree.command(name="offer", description="Offer a player to join your team.")
@app_commands.describe(target="The user to offer a spot on your team.")
async def offer(interaction: discord.Interaction, target: discord.Member):
    await interaction.response.defer(ephemeral=True)

    allowed_roles = {"Franchise Owner", "General Manager"}
    sender_roles = {r.name for r in interaction.user.roles}
    if not sender_roles & allowed_roles:
        await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
        return

    team_name = get_user_team(interaction.user)
    if not team_name:
        await interaction.followup.send("Couldn't determine your team. Make sure you have a valid team role.", ephemeral=True)
        return

    sender_rank = "Franchise Owner" if "Franchise Owner" in sender_roles else "General Manager"
    team_role = discord.utils.get(interaction.guild.roles, name=team_name)

    # Pull logo (optional fallback)
    if team_role and team_role.display_icon:
        logo_url = team_role.display_icon.url
    elif interaction.guild.icon:
        logo_url = interaction.guild.icon.url
    else:
        logo_url = discord.Embed.Empty

    embed = discord.Embed(
        title="You Have Been Offered a Spot",
        description=(
            f"{interaction.user.mention}, who is the **{sender_rank}** of the **{team_name}**, "
            f"has sent you an offer to join their team in **UFFL**."
        ),
        color=discord.Color.blurple()
    )
    embed.set_author(name="UFFL", icon_url=interaction.guild.icon.url if interaction.guild.icon else discord.Embed.Empty)
    embed.set_thumbnail(url=logo_url)
    embed.set_footer(text="Expires in 24 hours")

    view = OfferView(coach=interaction.user, team_name=team_name, guild=interaction.guild)

    try:
        await target.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Offer sent to {target.display_name} from **{team_name}**.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ That user's DMs are closed.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Unexpected error: `{e}`", ephemeral=True)

@bot.tree.command(name="release", description="Release a player from your team.")
@app_commands.describe(target="The member you want to release from your team.")
async def release(interaction: discord.Interaction, target: discord.Member):
    allowed_roles = {"Franchise Owner", "General Manager"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message(
            "Only Franchise Owners or General Managers can release players.",
            ephemeral=True
        )
        return

    team_name = get_user_team(interaction.user)
    if not team_name:
        await interaction.response.send_message(
            "Couldn't determine your team. Make sure you have a valid team role.",
            ephemeral=True
        )
        return

    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team_name)
    free_agents_role = discord.utils.get(guild.roles, name="Free agents")
    gm_role = discord.utils.get(guild.roles, name="General Manager")
    hc_role = discord.utils.get(guild.roles, name="Head Coach")

    # Make sure the target is actually on your team
    if team_role not in target.roles:
        await interaction.response.send_message(
            f"{target.display_name} is not on your team.",
            ephemeral=True
        )
        return

    # Remove team role and any GM/HC titles
    try:
        await target.remove_roles(team_role)
        if gm_role and gm_role in target.roles:
            await target.remove_roles(gm_role)
        if hc_role and hc_role in target.roles:
            await target.remove_roles(hc_role)
        if free_agents_role:
            await target.add_roles(free_agents_role)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to modify this member's roles.",
            ephemeral=True
        )
        return

    # DM the player who was released
    try:
        player_embed = discord.Embed(
            title="UFFL - Release Notice",
            description="You have been released from your team.",
            color=discord.Color.red()
        )
        player_embed.add_field(name="Team:", value=team_name, inline=True)
        player_embed.add_field(name="Coach:", value=interaction.user.mention, inline=True)
        player_embed.set_footer(text="You are now a Free Agent. Best of luck!")
        await target.send(embed=player_embed)
    except discord.Forbidden:
        print(f"❌ Could not DM {target.display_name}")

    # DM all FO and GM on the team (except the user who ran the command)
    notify_roles = ["Franchise Owner", "General Manager"]
    notified = set()

    for role_name in notify_roles:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            for member in role.members:
                if member == interaction.user:
                    continue  # skip sender
                if team_role in member.roles and member.id not in notified:
                    try:
                        alert_embed = discord.Embed(
                            title="🏈 UFFL - Player Released",
                            description=f"{target.display_name} has been released from **{team_name}**.",
                            color=discord.Color.red()
                        )
                        alert_embed.set_footer(text=f"Released by: {interaction.user.display_name}")
                        await member.send(embed=alert_embed)
                        notified.add(member.id)
                    except discord.Forbidden:
                        print(f"❌ Could not DM {member.display_name}")

    # Confirm success in chat
    await interaction.response.send_message(
        f"{target.display_name} has been released from **{team_name}**.",
        ephemeral=True
    )

@bot.tree.command(name="demand", description="Request to leave your current team.")
async def demand(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # ⛔ Prevent FOs from demanding
    if "Franchise Owner" in [r.name for r in interaction.user.roles]:
        await interaction.followup.send("Franchise Owners must transfer ownership before demanding a release.", ephemeral=True)
        return

    team_name = get_user_team(interaction.user)
    if not team_name:
        await interaction.followup.send("You are not on a team. Cannot demand.", ephemeral=True)
        return

    view = DemandConfirmView(user=interaction.user, team_name=team_name, guild=interaction.guild)
    await interaction.followup.send(
        f"Are you sure you want to **demand** a release from **{team_name}**?",
        view=view,
        ephemeral=True
    )

class FOTransferConfirmView(View):
    def __init__(self, bot: commands.Bot, old_fo: discord.Member, new_fo: discord.Member, guild: discord.Guild):
        super().__init__(timeout=60)
        self.bot = bot
        self.old_fo = old_fo
        self.new_fo = new_fo
        self.guild = guild

    @button(label="Yes, transfer FO role", style=discord.ButtonStyle.danger)
    async def confirm_transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.old_fo:
            await interaction.response.send_message("Only the current FO can confirm this.", ephemeral=True)
            return

        fo_role = discord.utils.get(self.guild.roles, name="Franchise Owner")
        team_name = get_user_team(self.old_fo)

        try:
            await self.new_fo.add_roles(fo_role)
            await self.old_fo.remove_roles(fo_role)

            await self.old_fo.send(
                f"You have successfully transferred the **Franchise Owner** role to {self.new_fo.display_name}. You still remain on **{team_name}**."
            )
            await self.new_fo.send(
                f"🏈 You are now the **Franchise Owner** of **{team_name}**. Lead your team well!"
            )

            await interaction.response.send_message(
                f"{self.new_fo.display_name} is now the **Franchise Owner**. You have stepped down but remain on **{team_name}**.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("I don’t have permission to change roles.", ephemeral=True)

        self.stop()

    @button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Franchise Owner transfer cancelled.", ephemeral=True)
        self.stop()


@bot.tree.command(name="promote", description="Promote a team member to HC, GM, or FO.")
@app_commands.describe(
    target="The member to promote.",
    role="Enter HC for Head Coach, GM for General Manager, or FO to transfer Franchise Owner status."
)
async def promote(interaction: discord.Interaction, target: discord.Member, role: str):
    role = role.upper().strip()
    valid_roles = {"HC": "Head Coach", "GM": "General Manager", "FO": "Franchise Owner"}

    if role not in valid_roles:
        await interaction.response.send_message("Invalid role. Choose HC, GM, or FO.", ephemeral=True)
        return

    if "Franchise Owner" not in [r.name for r in interaction.user.roles]:
        await interaction.response.send_message("Only Franchise Owners can promote members.", ephemeral=True)
        return

    team_name = get_user_team(interaction.user)
    if not team_name or get_user_team(target) != team_name:
        await interaction.response.send_message(f"{target.display_name} is not on your team.", ephemeral=True)
        return

    guild = interaction.guild
    new_role = discord.utils.get(guild.roles, name=valid_roles[role])
    if not new_role:
        await interaction.response.send_message(f"Role '{valid_roles[role]}' not found.", ephemeral=True)
        return

    if role == "FO":
        view = FOTransferConfirmView(bot, interaction.user, target, guild)
        await interaction.response.send_message(
            f"Are you sure you want to transfer the **Franchise Owner** role to {target.display_name}?",
            view=view,
            ephemeral=True
        )
        return

    try:
        await target.add_roles(new_role)
        print(f"[PROMOTE] {interaction.user.display_name} promoted {target.display_name} to {valid_roles[role]}.")

        try:
            await target.send(f"You’ve been promoted to **{valid_roles[role]}** on **{team_name}**.")
        except discord.Forbidden:
            print(f"[DM FAILED] Could not send DM to {target.display_name}.")

        await interaction.response.send_message(
            f"{target.display_name} has been promoted to **{valid_roles[role]}**.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message("I don’t have permission to update roles.", ephemeral=True)



@bot.tree.command(name="demote", description="Demote a team member from HC or GM.")
@app_commands.describe(
    target="The member to demote.",
    role="Enter HC to remove Head Coach or GM to remove General Manager."
)
async def demote(interaction: discord.Interaction, target: discord.Member, role: str):
    role = role.upper().strip()
    valid_roles = {"HC": "Head Coach", "GM": "General Manager"}

    # Validate role input
    if role not in valid_roles:
        await interaction.response.send_message("Invalid role. Please choose HC or GM.", ephemeral=True)
        return

    # Only FOs can demote
    if "Franchise Owner" not in [r.name for r in interaction.user.roles]:
        await interaction.response.send_message("Only Franchise Owners can demote team members.", ephemeral=True)
        return

    # Ensure both are on the same team
    team_name = get_user_team(interaction.user)
    if not team_name or get_user_team(target) != team_name:
        await interaction.response.send_message(f"{target.display_name} is not on your team ({team_name}).", ephemeral=True)
        return

    guild = interaction.guild
    demote_role = discord.utils.get(guild.roles, name=valid_roles[role])

    # Check if user has the role to be demoted from
    if not demote_role or demote_role not in target.roles:
        await interaction.response.send_message(f"{target.display_name} does not have the {valid_roles[role]} role.", ephemeral=True)
        return

    try:
        await target.remove_roles(demote_role)

        try:
            await target.send(
                f"🔻 You’ve been demoted from **{valid_roles[role]}**. You’re still a player on **{team_name}**."
            )
        except discord.Forbidden:
            print(f"❌ Could not DM {target.display_name}")

        await interaction.response.send_message(
            f"{target.display_name} has been demoted from **{valid_roles[role]}** to **player**.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to modify roles.", ephemeral=True)


@bot.tree.command(name="roster", description="View a full list of Franchise Owners and their team rosters.")
async def roster(interaction: discord.Interaction):
    allowed_roles = {"Commissioners", "Founder", "Franchise Owner"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
    gm_role = discord.utils.get(guild.roles, name="General Manager")
    hc_role = discord.utils.get(guild.roles, name="Head Coach")

    if not fo_role:
        await interaction.followup.send("❌ Franchise Owner role not found.", ephemeral=True)
        return

    team_data = {}

    for fo in fo_role.members:
        team_name = get_user_team(fo)
        if not team_name:
            continue

        team_role = discord.utils.get(guild.roles, name=team_name)
        if not team_role:
            continue

        # Get all members on the team
        all_team_members = team_role.members
        team_data[team_name] = {
            "fo": fo,
            "members": all_team_members
        }

    if not team_data:
        await interaction.followup.send("No teams or FOs with matching roles found.", ephemeral=True)
        return

    # Split large embed into chunks to avoid hitting 6000-character limit
    embeds = []
    chunk = discord.Embed(
        title="UFFL Team Roster",
        description="Franchise Owners and their complete team lineups",
        color=discord.Color.teal()
    )
    current_length = len(chunk.description)

    for team_name in sorted(team_data.keys()):
        fo = team_data[team_name]["fo"]
        members = team_data[team_name]["members"]
        total_members = len(members)

        team_list = f"**Franchise Owner**: {fo.display_name} (`{fo.id}`)\n"
        other_members = [m for m in members if m != fo]

        if other_members:
            for m in other_members:
                tags = []
                if gm_role in m.roles:
                    tags.append("GM")
                if hc_role in m.roles:
                    tags.append("HC")
                role_tag = f" ({', '.join(tags)})" if tags else ""
                team_list += f"• {m.display_name}{role_tag} (`{m.id}`)\n"
        else:
            team_list += "_No other members on this team._\n"

        # If the new field would make this embed too large, start a new one
        if current_length + len(team_list) >= 5500 or len(chunk.fields) >= 5:
            embeds.append(chunk)
            chunk = discord.Embed(
                title="UFFL Team Roster (continued)",
                color=discord.Color.teal()
            )
            current_length = 0

        chunk.add_field(
            name=f"🏈 {team_name} — {total_members} member{'s' if total_members != 1 else ''}",
            value=team_list,
            inline=False
        )
        current_length += len(team_list)

    embeds.append(chunk)

    # Try to send each chunk
    try:
        for e in embeds:
            await interaction.user.send(embed=e)
        await interaction.followup.send("📬 Sorted roster sent to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Could not send DM. Please make sure your DMs are open.", ephemeral=True)



@bot.tree.command(name="deadline_reminder", description="DM all Franchise Owners a deadline reminder.")
@app_commands.describe(deadline="Enter the deadline (e.g. April 20th at 11:59PM EST)")
async def deadline_reminder(interaction: discord.Interaction, deadline: str):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("You are not permitted to send deadline reminders.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    fo_role = discord.utils.get(interaction.guild.roles, name="Franchise Owner")
    if not fo_role:
        await interaction.followup.send("❌ Franchise Owner role not found on this server.", ephemeral=True)
        return

    embed = discord.Embed(
        title="UFFL Weekly Reminder",
        description=(
            "The deadline to complete your games is coming soon!\n\n"
            f"**🗓 Deadline: {deadline}**\n\n"
            "Please make sure all match details are submitted before the deadline.\n"
            "Contact league staff if any issues come up."
        ),
        color=discord.Color.orange()
    )
    embed.set_footer(text="UFFL Bot • Deadline Reminder")

    count = 0
    for member in fo_role.members:
        try:
            await member.send(embed=embed)
            count += 1
        except Exception as e:
            print(f"[DEADLINE REMINDER ERROR] Could not DM {member.display_name}: {e}")

    await interaction.followup.send(
        f"📨 Deadline reminder sent to {count} Franchise Owner(s).", ephemeral=True
    )

@bot.tree.command(name="debugcheck", description="Check if slash commands are active")
async def debugcheck(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Slash commands are live!", ephemeral=True)


@bot.tree.command(name="game_thread", description="Create a game thread between two teams. Automatically invites FOs, GMs, HCs, and staff.")
@app_commands.describe(team1="First team", team2="Second team")
async def game_thread(interaction: discord.Interaction, team1: str, team2: str):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.followup.send("❌ You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    channel = interaction.channel
    thread_name = f"{team1} vs {team2}"

    team_roles = [discord.utils.get(guild.roles, name=team1), discord.utils.get(guild.roles, name=team2)]
    if None in team_roles:
        await interaction.followup.send("❌ One or both team roles could not be found.", ephemeral=True)
        return

    ranking_roles = {"Franchise Owner", "General Manager", "Head Coach"}
    staff_roles = {"Founder", "Commissioners"}

    invited = set()

    for member in guild.members:
        user_role_names = {r.name for r in member.roles}
        on_team = any(tr.name in user_role_names for tr in team_roles)
        is_ranked = user_role_names & ranking_roles
        is_staff = user_role_names & staff_roles

        if (on_team and is_ranked) or is_staff:
            invited.add(member)

    try:
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080
        )

        for m in invited:
            try:
                await thread.add_user(m)
            except Exception as e:
                print(f"❌ Failed to add {m.display_name} to thread: {e}")

        await thread.send(f"🏈 Welcome to the game thread for **{team1} vs {team2}**!")
        await interaction.followup.send(f"✅ Game thread created and invited {len(invited)} users.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create thread: `{e}`", ephemeral=True)


@game_thread.autocomplete("team1")
async def team1_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES
        if current.lower() in team.lower()
    ][:25]

@game_thread.autocomplete("team2")
async def team2_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES
        if current.lower() in team.lower()
    ][:25]

@bot.tree.command(name="add_to_thread", description="Add a user to the current private thread.")
@app_commands.describe(user="The user to add to this thread")
async def add_to_thread(interaction: discord.Interaction, user: discord.Member):
    allowed_roles = {"Founder", "Commissioners", "Franchise Owner"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("⚠️ This command must be used inside a thread.", ephemeral=True)
        return

    thread: discord.Thread = interaction.channel

    if thread.type != discord.ChannelType.private_thread:
        await interaction.response.send_message("⚠️ This thread is not private. No need to manually add users.", ephemeral=True)
        return

    try:
        await thread.add_user(user)
        await interaction.response.send_message(f"✅ {user.mention} has been added to this thread.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don’t have permission to add that user.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to add user: `{e}`", ephemeral=True)

@bot.tree.command(name="close_thread", description="Delete the current thread. For use in UFFL game threads.")
async def close_thread(interaction: discord.Interaction):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to close threads.", ephemeral=True)
        return

    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("⚠️ This command can only be used inside a thread.", ephemeral=True)
        return

    await interaction.response.send_message("🧹 Closing and deleting this thread...", ephemeral=True)
    await interaction.channel.delete()



@bot.tree.command(name="disband", description="Disband a team and notify all affected members.")
@app_commands.describe(
    team="Select the team to disband.",
    reason="Explain the reason for disbanding the team."
)
async def disband(interaction: discord.Interaction, team: str, reason: str):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team)
    if not team_role:
        await interaction.followup.send(f"❌ Could not find the role for team **{team}**.", ephemeral=True)
        return

    ranking_roles = ["Franchise Owner", "General Manager", "Head Coach"]
    free_agents_role = discord.utils.get(guild.roles, name="Free agents")
    affected_members = team_role.members.copy()
    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-5))
    ).strftime("%B %d, %Y, %I:%M %p EST")

    # Capture FO/GM members BEFORE role removal
    users_to_notify = [
        member for member in affected_members
        if any(role.name in {"Franchise Owner", "General Manager"} for role in member.roles)
    ]

    # Remove team and ranking roles + assign Free agents
    for member in affected_members:
        roles_to_remove = [team_role]
        for rname in ranking_roles:
            role = discord.utils.get(guild.roles, name=rname)
            if role and role in member.roles:
                roles_to_remove.append(role)

        try:
            await member.remove_roles(*roles_to_remove)
            if free_agents_role:
                await member.add_roles(free_agents_role)
        except discord.Forbidden:
            print(f"❌ Could not modify roles for {member.display_name}")

    # DM users that were FO or GM
    notified = 0
    for member in users_to_notify:
        try:
            embed = discord.Embed(
                title="📬 UFFL - Team Disbanded",
                description=f"Your team **{team}** has been officially disbanded.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Disbanded by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Date", value=timestamp, inline=True)
            embed.set_footer(text="You are now a Free Agent.")

            await member.send(embed=embed)
            await asyncio.sleep(1)  # rate limit protection
            notified += 1
        except Exception as e:
            print(f"❌ Could not DM {member.display_name}: {e}")

    await interaction.followup.send(
        f"✅ Team **{team}** has been disbanded. {len(affected_members)} members affected. "
        f"{notified} FO/GM notified by DM.",
        ephemeral=True
    )

@disband.autocomplete("team")
async def disband_team_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES
        if current.lower() in team.lower()
    ][:25]


@bot.tree.command(name="gametime", description="Announce a scheduled UFFL match with team FOs, time, and private server link.")
@app_commands.describe(
    team1="First team name",
    team2="Second team name",
    time_est="Time the match is scheduled to start (in EST)",
    private_server_link="Link to the private server"
)
async def gametime(interaction: discord.Interaction, team1: str, team2: str, time_est: str, private_server_link: str):
    allowed_roles = {"Franchise Owner", "Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    role1 = discord.utils.get(guild.roles, name=team1)
    role2 = discord.utils.get(guild.roles, name=team2)

    if not role1 or not role2:
        await interaction.followup.send("❌ One or both team roles were not found.", ephemeral=True)
        return

    def find_fo(role):
        fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
        if not fo_role:
            return None
        for member in fo_role.members:
            if role in member.roles:
                return member
        return None

    fo1 = find_fo(role1)
    fo2 = find_fo(role2)

    if not fo1 or not fo2:
        await interaction.followup.send("❌ Could not find Franchise Owner(s) for one or both teams.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏈 UFFL MATCH",
        description=(
            f"**{team1}** vs **{team2}**\n"
            f"• **Franchise Owners:** {fo1.mention} vs {fo2.mention}\n"
            f"• **Kickoff Time:** {time_est} (EST)\n"
            f"• [**Join Here!**]({private_server_link})"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="UFFL Bot • Game Schedule")

    channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if not channel:
        await interaction.followup.send("❌ Announcement channel not found. Please check the channel ID.", ephemeral=True)
        return

    await channel.send(embed=embed)
    await interaction.followup.send("📣 Game announcement sent!", ephemeral=True)


@gametime.autocomplete("team1")
async def gametime_team1_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES if current.lower() in team.lower()
    ][:25]

@gametime.autocomplete("team2")
async def gametime_team2_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES if current.lower() in team.lower()
    ][:25]


@bot.tree.command(name="give_role", description="Assign the FO role and an available team role to a user.")
@app_commands.describe(
    user="The user to assign the Franchise Owner role to.",
    team="Select the team to assign."
)
async def give_role(interaction: discord.Interaction, user: discord.Member, team: str):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team)
    fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
    free_agents_role = discord.utils.get(guild.roles, name="Free agents")

    if not team_role or not fo_role:
        await interaction.response.send_message("❌ Role not found. Please check your server's roles.", ephemeral=True)
        return

    if any(team_role in member.roles for member in guild.members):
        await interaction.response.send_message(f"❌ The team **{team}** is already taken.", ephemeral=True)
        return

    try:
        await user.add_roles(fo_role, team_role)

        # Remove Free agents role if present
        if free_agents_role and free_agents_role in user.roles:
            await user.remove_roles(free_agents_role)

        # DM the new FO (target user)
        try:
            embed = discord.Embed(
                title="🏈 UFFL - You're a Franchise Owner!",
                description=f"You've been assigned as the **Franchise Owner** of **{team}**.",
                color=discord.Color.green()
            )
            embed.set_footer(text="Lead your team with pride.")
            await user.send(embed=embed)
        except discord.Forbidden:
            print(f"❌ Could not DM {user.display_name}")

        # Respond to the command user only once
        await interaction.response.send_message(f"✅ {user.mention} has been made FO of **{team}**.", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to assign roles to this user.", ephemeral=True)


@give_role.autocomplete("team")
async def give_role_team_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild = interaction.guild
    unavailable_teams = {role.name for member in guild.members for role in member.roles if role.name in TEAM_NAMES}
    available_teams = [team for team in TEAM_NAMES if team not in unavailable_teams]

    return [
        app_commands.Choice(name=team, value=team)
        for team in available_teams if current.lower() in team.lower()
    ][:25]


@bot.tree.command(name="submit_score", description="Submit a final score between two teams for stat tracking.")
@app_commands.describe(
    team1="First team name",
    score1="Score for the first team",
    team2="Second team name",
    score2="Score for the second team",
    season="Enter the season (e.g. 2025)"
)
async def submit_score(interaction: discord.Interaction, team1: str, score1: int, team2: str, score2: int, season: str = "2025"):
    allowed_roles = {"Founder", "Commissioners", "Franchise Owner"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to submit scores.", ephemeral=True)
        return

    if team1 == team2:
        await interaction.response.send_message("❌ Team names must be different.", ephemeral=True)
        return

    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    data.setdefault(season, {})
    for team in [team1, team2]:
        data[season].setdefault(team, [])

    today = datetime.datetime.now().strftime("%m-%d-%Y")

    data[season][team1].append({
        "opponent": team2,
        "team_score": score1,
        "opponent_score": score2,
        "date": today
    })

    data[season][team2].append({
        "opponent": team1,
        "team_score": score2,
        "opponent_score": score1,
        "date": today
    })

    with open("uffl_scores.json", "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(
        f"✅ Score submitted:\n• {team1}: {score1}\n• {team2}: {score2}\n• Season: {season}", ephemeral=True
    )

@bot.tree.command(name="delete_score", description="Delete a previously submitted score by date.")
@app_commands.describe(
    team="The team you are removing the score for",
    opponent="Opponent team",
    date="The date of the game (MM-DD-YYYY)",
    season="Season (e.g. 2025)"
)
async def delete_score(interaction: discord.Interaction, team: str, opponent: str, date: str, season: str = "2025"):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to delete scores.", ephemeral=True)
        return

    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await interaction.response.send_message("❌ Score data file not found.", ephemeral=True)
        return

    season_data = data.get(season, {})
    team_games = season_data.get(team, [])
    opponent_games = season_data.get(opponent, [])

    before = len(team_games)

    # Remove from team's record
    team_games = [g for g in team_games if not (g["opponent"] == opponent and g["date"] == date)]
    opponent_games = [g for g in opponent_games if not (g["opponent"] == team and g["date"] == date)]

    after = len(team_games)

    if before == after:
        await interaction.response.send_message("⚠️ No matching score found. Double check the team, opponent, and date (MM-DD-YYYY).", ephemeral=True)
        return

    data[season][team] = team_games
    data[season][opponent] = opponent_games

    with open("uffl_scores.json", "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(
        f"🗑️ Score deleted between **{team}** and **{opponent}** on `{date}`.", ephemeral=True
    )

@bot.tree.command(name="view_scores", description="View all recorded scores for a team.")
@app_commands.describe(team="The team to view scores for", season="Season (e.g. 2025)")
async def view_scores(interaction: discord.Interaction, team: str, season: str = "2025"):
    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await interaction.response.send_message("❌ Score data file not found.", ephemeral=True)
        return

    team_games = data.get(season, {}).get(team, [])

    if not team_games:
        await interaction.response.send_message(f"📭 No scores found for **{team}** in season {season}.", ephemeral=True)
        return

    msg = f"📋 Scores for **{team}**:\n"
    for g in team_games:
        msg += f"- vs **{g['opponent']}** on `{g['date']}` → {g['team_score']}-{g['opponent_score']}\n"

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="team_info", description="View stats for a specific team in a given season.")
@app_commands.describe(
    team="The team name",
    season="Season to query (e.g. 2025)"
)
async def team_info(interaction: discord.Interaction, team: str, season: str = "2025"):
    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await interaction.response.send_message("⚠️ No score data found yet.", ephemeral=True)
        return

    season_data = data.get(season, {})
    team_games = season_data.get(team, [])

    if not team_games:
        await interaction.response.send_message(f"📭 No data for **{team}** in season {season}.", ephemeral=True)
        return

    wins = sum(1 for g in team_games if g["team_score"] > g["opponent_score"])
    losses = sum(1 for g in team_games if g["team_score"] < g["opponent_score"])
    scores = [g["team_score"] for g in team_games]
    total_points = sum(scores)
    points_allowed = sum(g["opponent_score"] for g in team_games)
    avg_score = total_points / len(scores)
    point_diff = total_points - points_allowed

    embed = discord.Embed(
        title=f"📊 {team} Team Stats ({season})",
        color=discord.Color.green()
    )
    embed.add_field(name="Wins", value=str(wins))
    embed.add_field(name="Losses", value=str(losses))
    embed.add_field(name="Games Played", value=str(len(scores)))
    embed.add_field(name="Average Score", value=f"{avg_score:.2f}")
    embed.add_field(name="Highest Score", value=str(max(scores)))
    embed.add_field(name="Lowest Score", value=str(min(scores)))
    embed.add_field(name="Point Differential", value=f"{point_diff:+}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="View the top teams in a selected stat category.")
@app_commands.describe(
    category="Select the stat category to sort by.",
    season="Enter the season (e.g. 2025)"
)
@app_commands.choices(category=[
    app_commands.Choice(name="Total Points", value="Total Points"),
    app_commands.Choice(name="Average Points", value="Average Points"),
    app_commands.Choice(name="Points in Single Game", value="Points in Single Game"),
    app_commands.Choice(name="Point Differential", value="Point Differential"),
    app_commands.Choice(name="Wins", value="Wins"),
    app_commands.Choice(name="Losses", value="Losses")
])
async def leaderboard(interaction: discord.Interaction, category: app_commands.Choice[str], season: str = "2025"):
    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await interaction.response.send_message("❌ No score data found.", ephemeral=True)
        return

    season_data = data.get(season, {})
    if not season_data:
        await interaction.response.send_message(f"❌ No data found for season {season}.", ephemeral=True)
        return

    leaderboard = []
    for team, games in season_data.items():
        total_points = sum(g["team_score"] for g in games)
        games_played = len(games)
        avg_points = total_points / games_played if games_played > 0 else 0
        max_points = max((g["team_score"] for g in games), default=0)
        total_allowed = sum(g["opponent_score"] for g in games)
        point_diff = total_points - total_allowed
        wins = sum(1 for g in games if g["team_score"] > g["opponent_score"])
        losses = sum(1 for g in games if g["team_score"] < g["opponent_score"])

        stats = {
            "Team": team,
            "Total Points": total_points,
            "Average Points": avg_points,
            "Points in Single Game": max_points,
            "Point Differential": point_diff,
            "Wins": wins,
            "Losses": losses
        }

        leaderboard.append(stats)

    leaderboard.sort(key=lambda x: x[category.value], reverse=True)
    top5 = leaderboard[:5]

    embed = discord.Embed(
        title=f"📊 Leaderboard — {category.name}",
        description=f"_Season: {season}_",
        color=discord.Color.purple()
    )

    for idx, entry in enumerate(top5, start=1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        value = f"**{entry['Team']}** — `{entry[category.value]}`"
        embed.add_field(name=f"{medal}", value=value, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="group_create", description="Add up to 4 teams into an existing group (A–D).")
@app_commands.describe(
    group="Select which group to add to (A, B, C, or D).",
    team1="Optional team to add to group",
    team2="Optional team to add to group",
    team3="Optional team to add to group",
    team4="Optional team to add to group"
)
@app_commands.choices(group=[
    app_commands.Choice(name="Group A", value="A"),
    app_commands.Choice(name="Group B", value="B"),
    app_commands.Choice(name="Group C", value="C"),
    app_commands.Choice(name="Group D", value="D")
])
async def group_create(interaction: discord.Interaction, group: app_commands.Choice[str],
    team1: str = None, team2: str = None, team3: str = None, team4: str = None):

    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have permission to update groups.", ephemeral=True)
        return

    # Filter out None and validate teams
    new_teams = [t for t in [team1, team2, team3, team4] if t]
    if not new_teams:
        await interaction.response.send_message("⚠️ Please provide at least one team to add.", ephemeral=True)
        return

    if any(t not in TEAM_NAMES for t in new_teams):
        await interaction.response.send_message("❌ One or more teams are invalid.", ephemeral=True)
        return

    try:
        with open("uffl_groups.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"A": [], "B": [], "C": [], "D": []}

    group_key = group.value
    current = data.get(group_key, [])

    # Add new teams, prevent duplicates
    for team in new_teams:
        if team not in current:
            current.append(team)

    data[group_key] = current

    with open("uffl_groups.json", "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(
        f"✅ Group {group_key} now contains: {', '.join(data[group_key])}", ephemeral=True
    )

@bot.tree.command(name="group_reset", description="Reset all groups or a specific group (A–D).")
@app_commands.describe(
    target="Select which group to reset or choose ALL to reset everything."
)
@app_commands.choices(target=[
    app_commands.Choice(name="All Groups", value="ALL"),
    app_commands.Choice(name="Group A", value="A"),
    app_commands.Choice(name="Group B", value="B"),
    app_commands.Choice(name="Group C", value="C"),
    app_commands.Choice(name="Group D", value="D")
])
async def group_reset(interaction: discord.Interaction, target: app_commands.Choice[str]):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to reset groups.", ephemeral=True)
        return

    try:
        with open("uffl_groups.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"A": [], "B": [], "C": [], "D": []}

    if target.value == "ALL":
        for key in ["A", "B", "C", "D"]:
            data[key] = []
        msg = "🔄 All groups (A–D) have been reset."
    else:
        data[target.value] = []
        msg = f"🧹 Group {target.value} has been cleared."

    with open("uffl_groups.json", "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="group_info", description="View the current teams in all UFFL groups.")
async def group_info(interaction: discord.Interaction):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to view group info.", ephemeral=True)
        return

    try:
        with open("uffl_groups.json", "r") as f:
            groups = json.load(f)
    except FileNotFoundError:
        groups = {"A": [], "B": [], "C": [], "D": []}

    embed = discord.Embed(
        title="📘 UFFL Group Info",
        description="Current team assignments by group.",
        color=discord.Color.blue()
    )

    for key in ["A", "B", "C", "D"]:
        teams = groups.get(key, [])
        value = "\n".join(f"• {team}" for team in teams) if teams else "_No teams assigned yet_"
        embed.add_field(name=f"Group {key}", value=value, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="group_thread", description="Create a private thread for a group (A–D) with all team staff.")
@app_commands.describe(group="Choose the group to create a thread for.")
@app_commands.choices(group=[
    app_commands.Choice(name="Group A", value="A"),
    app_commands.Choice(name="Group B", value="B"),
    app_commands.Choice(name="Group C", value="C"),
    app_commands.Choice(name="Group D", value="D")
])
async def group_thread(interaction: discord.Interaction, group: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.followup.send("❌ You don't have permission to use this command.", ephemeral=True)
        return

    try:
        with open("uffl_groups.json", "r") as f:
            groups = json.load(f)
    except FileNotFoundError:
        await interaction.followup.send("❌ Group data file not found.", ephemeral=True)
        return

    group_key = group.value
    group_teams = groups.get(group_key, [])
    if not group_teams:
        await interaction.followup.send(f"❌ No teams found in Group {group_key}.", ephemeral=True)
        return

    guild = interaction.guild
    channel = interaction.channel

    invited = set()

    team_roles = [discord.utils.get(guild.roles, name=team) for team in group_teams]
    staff_roles = {"Franchise Owner", "General Manager", "Head Coach", "Founder", "Commissioners"}

    for member in guild.members:
        user_roles = {r.name for r in member.roles}

        on_team = any(role.name in user_roles for role in team_roles if role)
        is_ranked = user_roles & {"Franchise Owner", "General Manager", "Head Coach"}
        is_staff = user_roles & {"Founder", "Commissioners"}

        if (on_team and is_ranked) or is_staff:
            invited.add(member)

    try:
        thread = await channel.create_thread(
            name=f"Group {group_key} Thread",
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080,
            invitable=False  # prevents unwanted invites, optional
        )

        for user in invited:
            try:
                await thread.add_user(user)
            except Exception as e:
                print(f"❌ Failed to add {user.display_name} to thread: {e}")


        await thread.send(f"📣 Welcome to the thread for **Group {group_key}**!")
        await interaction.response.send_message(
            f"✅ Group {group_key} thread created. {len(invited)} users invited.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create thread: `{e}`", ephemeral=True)

@bot.tree.command(name="fo_dashboard", description="FO dashboard: roster, recent games, record, and groupmates (sent via DM).")
async def fo_dashboard(interaction: discord.Interaction):
    if "Franchise Owner" not in [role.name for role in interaction.user.roles]:
        await interaction.response.send_message("❌ This command is only available to Franchise Owners.", ephemeral=True)
        return

    guild = interaction.guild
    team_name = get_user_team(interaction.user)
    if not team_name:
        await interaction.response.send_message("❌ Could not determine your team role.", ephemeral=True)
        return

    team_role = discord.utils.get(guild.roles, name=team_name)
    gm_role = discord.utils.get(guild.roles, name="General Manager")
    hc_role = discord.utils.get(guild.roles, name="Head Coach")

    roster = team_role.members if team_role else []
    gm = [m.display_name for m in roster if gm_role in m.roles]
    hc = [m.display_name for m in roster if hc_role in m.roles]
    players = [
        f"{m.display_name} {'(GM)' if gm_role in m.roles else ''} {'(HC)' if hc_role in m.roles else ''}".strip()
        for m in roster if m != interaction.user
    ]

    # Load recent games and calculate record
    recent_games = []
    wins = 0
    losses = 0
    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
        season_games = data.get("2025", {}).get(team_name, [])
        sorted_games = sorted(season_games, key=lambda g: g["date"], reverse=True)
        for g in sorted_games:
            result = "W" if g["team_score"] > g["opponent_score"] else "L"
            if result == "W":
                wins += 1
            else:
                losses += 1
        for g in sorted_games[:3]:
            result = "W" if g["team_score"] > g["opponent_score"] else "L"
            line = f"{g['date']}: {result} vs {g['opponent']} ({g['team_score']}-{g['opponent_score']})"
            recent_games.append(line)
    except Exception:
        recent_games = ["No recent games logged."]

    # Load groupmates
    groupmates = []
    try:
        with open("uffl_groups.json", "r") as f:
            groups = json.load(f)
        for group_label, teams in groups.items():
            if team_name in teams:
                groupmates = [t for t in teams if t != team_name]
                break
    except Exception:
        groupmates = []

    # Build DM embed
    embed = discord.Embed(
        title=f"📊 FO Dashboard — {team_name}",
        color=discord.Color.orange()
    )
    embed.add_field(name="Franchise Owner", value=interaction.user.display_name, inline=False)
    embed.add_field(name="General Manager", value=", ".join(gm) or "_None_", inline=True)
    embed.add_field(name="Head Coach", value=", ".join(hc) or "_None_", inline=True)
    embed.add_field(name="Roster Size", value=f"{len(roster)} players", inline=True)
    embed.add_field(name="Full Roster", value="\n".join(players) or "_No other players_", inline=False)
    embed.add_field(name="Season Record", value=f"{wins} Wins – {losses} Losses", inline=True)
    embed.add_field(name="Last 3 Games", value="\n".join(recent_games), inline=False)
    embed.add_field(name="Teams in Your Group", value="\n".join(groupmates) or "_Not assigned to a group_", inline=False)
    embed.set_footer(text="UFFL Bot • FO Utility")

    try:
        await interaction.user.send(embed=embed)
        await interaction.response.send_message("📬 Dashboard sent to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Could not send DM. Please make sure your DMs are open.", ephemeral=True)

@bot.tree.command(name="team_dashboard", description="View detailed info about any UFFL team.")
@app_commands.describe(team="Choose a team to view their full dashboard.")
async def team_dashboard(interaction: discord.Interaction, team: str):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ Only Founders and Commissioners can use this command.", ephemeral=True)
        return

    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team)
    if not team_role:
        await interaction.response.send_message("❌ That team role was not found.", ephemeral=True)
        return

    fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
    gm_role = discord.utils.get(guild.roles, name="General Manager")
    hc_role = discord.utils.get(guild.roles, name="Head Coach")

    # Find FO for the team
    fo = next((m for m in fo_role.members if team_role in m.roles), None)
    roster = team_role.members
    gm = [m.display_name for m in roster if gm_role in m.roles]
    hc = [m.display_name for m in roster if hc_role in m.roles]
    players = [
        f"{m.display_name} {'(GM)' if gm_role in m.roles else ''} {'(HC)' if hc_role in m.roles else ''}".strip()
        for m in roster if m != fo
    ]

    # Load recent games and calculate record
    recent_games = []
    wins = 0
    losses = 0
    try:
        with open("uffl_scores.json", "r") as f:
            data = json.load(f)
        season_games = data.get("2025", {}).get(team, [])
        sorted_games = sorted(season_games, key=lambda g: g["date"], reverse=True)
        for g in sorted_games:
            result = "W" if g["team_score"] > g["opponent_score"] else "L"
            if result == "W":
                wins += 1
            else:
                losses += 1
        for g in sorted_games[:3]:
            result = "W" if g["team_score"] > g["opponent_score"] else "L"
            line = f"{g['date']}: {result} vs {g['opponent']} ({g['team_score']}-{g['opponent_score']})"
            recent_games.append(line)
    except Exception:
        recent_games = ["No recent games logged."]

    # Load groupmates
    groupmates = []
    try:
        with open("uffl_groups.json", "r") as f:
            groups = json.load(f)
        for group_label, teams in groups.items():
            if team in teams:
                groupmates = [t for t in teams if t != team]
                break
    except Exception:
        groupmates = []

    # Build embed
    embed = discord.Embed(
        title=f"📊 Team Dashboard — {team}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Franchise Owner", value=fo.display_name if fo else "_Unassigned_", inline=False)
    embed.add_field(name="General Manager", value=", ".join(gm) or "_None_", inline=True)
    embed.add_field(name="Head Coach", value=", ".join(hc) or "_None_", inline=True)
    embed.add_field(name="Roster Size", value=f"{len(roster)} players", inline=True)
    embed.add_field(name="Full Roster", value="\n".join(players) or "_No other players_", inline=False)
    embed.add_field(name="Season Record", value=f"{wins} Wins – {losses} Losses", inline=True)
    embed.add_field(name="Last 3 Games", value="\n".join(recent_games), inline=False)
    embed.add_field(name="Teams in Group", value="\n".join(groupmates) or "_Not assigned to a group_", inline=False)
    embed.set_footer(text="UFFL Bot • Admin Utility")

    try:
        await interaction.user.send(embed=embed)
        await interaction.response.send_message("📬 Team dashboard sent to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Could not send DM. Please make sure your DMs are open.", ephemeral=True)

@bot.tree.command(name="submit_stats", description="Manually submit a stat line for a player.")
@app_commands.describe(
    user="The player you're submitting stats for",
    position="Player's position (e.g. Passer, Runner, Corner...)",
    stat_category="Stat name (e.g. TDs, Yards, INTs...)",
    value="Stat value (number or text)"
)
async def submit_stats(
    interaction: discord.Interaction,
    user: discord.Member,
    position: str,
    stat_category: str,
    value: str  # use str to allow values like '25/48'
):
    allowed_roles = {"Founder", "Commissioners"}
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    position = position.title().strip()
    stat_category = stat_category.strip()
    user_id = str(user.id)

    try:
        with open("uffl_player_stats.json", "r") as f:
            stats_data = json.load(f)
    except FileNotFoundError:
        stats_data = {}

    stats_data.setdefault(position, {})
    stats_data[position].setdefault(user_id, {"name": user.display_name, "games": []})

    # Create new game entry
    stats_data[position][user_id]["games"].append({
        stat_category: try_parse_stat(value)
    })

    with open("uffl_player_stats.json", "w") as f:
        json.dump(stats_data, f, indent=4)

    await interaction.response.send_message(
        f"✅ Added stat for **{user.display_name}** ({position}): `{stat_category} = {value}`",
        ephemeral=True
    )

def try_parse_stat(value):
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value  # keep as string for things like "25/48"

@bot.tree.command(name="stats_lb", description="View the top 3 players in a specific stat and position.")
@app_commands.describe(
    position="Player position (Passer, Runner, etc.)",
    stat_category="Stat to rank by (e.g. Yards, TDs, Comp/Att...)"
)
async def stats_lb(interaction: discord.Interaction, position: str, stat_category: str):
    position = position.title().strip()
    stat_category = stat_category.strip()

    try:
        with open("uffl_player_stats.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await interaction.response.send_message("❌ No stats data found yet.", ephemeral=True)
        return

    if position not in data:
        await interaction.response.send_message(f"❌ No data for position `{position}`.", ephemeral=True)
        return

    leaderboard = []

    for user_id, player_data in data[position].items():
        total = 0
        count = 0
        best = None

        for game in player_data.get("games", []):
            stat_val = game.get(stat_category)
            if stat_val is None:
                continue

            # Normalize stat types
            if isinstance(stat_val, str) and "/" in stat_val:
                continue  # skip string ratios like "25/48"
            try:
                val = float(stat_val)
            except:
                continue

            total += val
            count += 1
            if best is None or val > best:
                best = val

        if count == 0:
            continue

        final_score = total if stat_category.lower() in ["tds", "yards", "int", "misses", "tackles", "sacks", "yac", "attempts"] else (total / count)
        leaderboard.append((user_id, player_data["name"], final_score))

    if not leaderboard:
        await interaction.response.send_message("📭 No data found for that stat.", ephemeral=True)
        return

    leaderboard.sort(key=lambda x: x[2], reverse=True)
    top3 = leaderboard[:3]

    embed = discord.Embed(
        title=f"🏆 Top 3 — {position} - {stat_category}",
        description="Sorted by highest stat value.",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]
    for idx, (uid, name, value) in enumerate(top3):
        embed.add_field(
            name=f"{medals[idx]} {name}",
            value=f"`{value}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.context_menu(name="Import Stats")
async def Import_Stats(interaction: discord.Interaction, message: discord.Message):
    attachments = message.attachments
    if not attachments:
        await interaction.response.send_message("❌ No images found on that message.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    results = {}
    for image in attachments:
        try:
            img_bytes = await image.read()
            img = Image.open(io.BytesIO(img_bytes)).convert("L")
            img = img.point(lambda p: 255 if p > 160 else 0)  # binarize
            text = pytesseract.image_to_string(img)
            await interaction.followup.send(
                content=f"🧪 OCR extracted text:\n```{text[:1800]}```",
                ephemeral=True
            )
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            category = detect_stat_category(lines)


            if not category:
                continue

            parsed = parse_stat_lines(lines, category)
            if not parsed:
                continue

            if category not in results:
                results[category] = []
            results[category].extend(parsed)

        except Exception as e:
            print(f"[IMPORT ERROR]: {e}")
            continue

    if not results:
        await interaction.followup.send("❌ No valid stats detected in the uploaded images.", ephemeral=True)
        return

    embeds = []
    for position, players in results.items():
        embed = discord.Embed(title=f"📊 {position} Stats", color=discord.Color.green())
        for player in players:
            lines = [f"`{k}`: {v}" for k, v in player["stats"].items()]
            embed.add_field(name=player["name"], value="\n".join(lines), inline=False)
        embeds.append(embed)

    await interaction.followup.send(
        content="✅ Review the stats below. You can now manually submit or track them.",
        embeds=embeds,
        ephemeral=True
    )


def parse_stat_lines(lines, category):
    players = []
    header_row = None
    column_names = []

    # Step 1: Find the header
    for line in lines:
        if line.lower().startswith("player"):
            header_row = line
            break

    if not header_row:
        return []

    # Step 2: Parse header to get stat names
    raw_headers = re.split(r'\s{2,}|\t+', header_row.strip())
    if not raw_headers or raw_headers[0].lower() != "player":
        return []

    column_names = raw_headers[1:]  # Skip "Player"

    # Step 3: Parse rows that follow
    parsing = False
    for line in lines:
        if line == header_row:
            parsing = True
            continue
        if not parsing:
            continue

        parts = re.split(r'\s{2,}|\t+', line.strip())
        if len(parts) < 2:
            continue

        name = parts[0]
        stat_values = parts[1:]

        stats = {}
        for i, val in enumerate(stat_values):
            if i < len(column_names):
                stats[column_names[i]] = val

        players.append({
            "name": name,
            "stats": stats
        })

    return players


def find_or_create_player_id(player_data, name):
    for uid, pdata in player_data.items():
        if pdata["name"].lower() == name.lower():
            return uid
    return str(max([int(uid) for uid in player_data.keys()] + [100000]) + 1)

def detect_stat_category(lines):
    categories = {
        "Passer": ["Comp", "Att", "TD", "INT", "Rating", "Yards"],
        "Runner": ["Misses", "Attempts", "Yards", "Long"],
        "Receiver": ["Catches", "Targets", "TD", "YAC", "INT", "Allowed", "Yards", "Long"],
        "Corner": ["Deny", "Swats", "INT", "CompAllowed", "Rating"],
        "Defender": ["Tackles", "Misses", "Sacks", "Safeties", "ForceFumb", "Rec.Fumb"],
        "Kicker": ["Good", "Att", "Long", ">47"]
    }

    for category, keywords in categories.items():
        for line in lines:
            for kw in keywords:
                if kw.lower() in line.lower().replace(" ", ""):  # fuzzier matching
                    return category
    return None



@bot.tree.command(name="botcmds", description="DMs you a list of all bot commands.")
async def botcmds(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)

        # Path to the .txt file (must be in your deployed folder or properly pathed)
        file_path = "uffl_bot_commands_2025-04-15_15-41.txt"

        # Check if the file exists
        if not os.path.isfile(file_path):
            await interaction.followup.send("❌ Command guide file not found.", ephemeral=True)
            return

        # DM the user with the file attached
        with open(file_path, "rb") as f:
            await interaction.user.send(
                content="Here’s a full list of bot commands and how they work:",
                file=discord.File(f, filename=os.path.basename(file_path))
            )

        await interaction.followup.send("📬 Command guide sent to your DMs.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ I couldn't DM you. Please make sure your DMs are open.", ephemeral=True)
    except Exception as e:
        print(f"[botcmds ERROR] {e}")
        await interaction.followup.send("❌ Something went wrong while trying to send the command guide.", ephemeral=True)


from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "UFFL Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


# ✅ AUTOCOMPLETE GOES HERE
@submit_score.autocomplete("team1")
@submit_score.autocomplete("team2")
@delete_score.autocomplete("team")
@delete_score.autocomplete("opponent")
@team_info.autocomplete("team")
async def team_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES if current.lower() in team.lower()
    ][:25]

@team_dashboard.autocomplete("team")
async def team_dashboard_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=team, value=team)
        for team in TEAM_NAMES if current.lower() in team.lower()
    ][:25]


user_offense_counts = defaultdict(int)
message_timestamps = defaultdict(lambda: deque(maxlen=5)) 
message_contents = defaultdict(lambda: deque(maxlen=5))   
SPAM_TIME_WINDOW = 5

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not message.content:
        await bot.process_commands(message)
        return


    EXCLUDED_USER_IDS = [
        703001711458910740,
        1329697045476409372,
        1361143016726991041,
        888875111766196255,
        797306007579656223
    ]
    EXCLUDED_ROLES = {"Founder", "Commissioners", "UFFL BOT!"}

    if (
        message.author.id in EXCLUDED_USER_IDS
        or any(role.name in EXCLUDED_ROLES for role in message.author.roles)
        or message.author.guild_permissions.manage_messages
    ):
        await bot.process_commands(message)
        return

    now = time.time()
    content = message.content.lower()
    user_id = message.author.id

    message_timestamps[user_id].append(now)
    message_contents[user_id].append(content)

    log_channel = bot.get_channel(MOD_LOG_CHANNEL_ID)

    # ✅ Blacklist check
    blacklisted_words = [
        "join my server", "join my discord", ".gg"
    ]
    contains_blacklisted = any(word in content for word in blacklisted_words) or \
        "discord.gg/" in content or "discord.com/invite/" in content

    if contains_blacklisted:
        reason = "blacklisted content"
        dm_msg = "⚠️ Please do not post blacklisted links or phrases in the server."
    else:
        # ✅ Spam check — 5 messages in 10s OR 3+ repeated messages
        timestamps = message_timestamps[user_id]
        contents = message_contents[user_id]
        spam_by_speed = len(timestamps) == 5 and (now - timestamps[0] < SPAM_TIME_WINDOW)
        repeated_count = contents.count(contents[-1])
        spam_by_repetition = repeated_count >= 3

        if not spam_by_speed and not spam_by_repetition:
            await bot.process_commands(message)
            return

        try:
            await message.delete()
        except discord.Forbidden:
            print("⚠️ Can't delete spam message.")

        reason = "spamming"
        dm_msg = "⚠️ Please do not spam messages in the server."

    offense_count = user_offense_counts[user_id] + 1
    user_offense_counts[user_id] = offense_count


    action_taken = ""
    try:
        if offense_count == 1:
            await message.author.send(dm_msg)
            action_taken = "Sent DM warning"
        elif offense_count == 2:
            await message.author.timeout(timedelta(minutes=5), reason=f"2nd offense - {reason}")
            await message.channel.send(f"{message.author.mention} has been timed out for 5 minutes.", delete_after=5)
            action_taken = "5-minute timeout"
        elif offense_count == 3:
            await message.author.timeout(timedelta(hours=3), reason=f"3rd offense - {reason}")
            await message.channel.send(f"{message.author.mention} has been timed out for 3 hours.", delete_after=5)
            action_taken = "3-hour timeout"
        elif offense_count >= 4:
            await message.author.kick(reason=f"4th offense - repeated {reason}")
            await message.channel.send(f"{message.author.mention} has been kicked for repeated violations.", delete_after=5)
            action_taken = "User kicked"
    except discord.Forbidden:
        action_taken = "❌ Missing permissions to take action"
    except Exception as e:
        action_taken = f"❌ Error: {e}"

    if log_channel:
        await log_channel.send(
            f"🚨 **{reason.title()} Violation**\n"
            f"User: {message.author.mention} (`{user_id}`)\n"
            f"Offense #{offense_count}\n"
            f"Action Taken: {action_taken}\n"
            f"Message Content: `{message.content[:500]}`"
        )



@group_create.autocomplete("team1")
@group_create.autocomplete("team2")
@group_create.autocomplete("team3")
@group_create.autocomplete("team4")
async def group_create_team_autocomplete(interaction: discord.Interaction, current: str):
    guild = interaction.guild
    if not guild:
        return []

    fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
    if not fo_role:
        return []

    # Collect all team roles currently assigned to a user with FO role
    teams_with_fo = set()
    for member in fo_role.members:
        for role in member.roles:
            if role.name in TEAM_NAMES:
                teams_with_fo.add(role.name)

    # Filter by current text
    return [
        app_commands.Choice(name=team, value=team)
        for team in sorted(teams_with_fo)
        if current.lower() in team.lower()
    ][:25]


import os
bot.run(os.environ["DISCORD_TOKEN"])
