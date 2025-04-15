import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, button

GUILD_ID = 1307397558787899515  # Define GUILD_ID at the top!

TEAM_NAMES = [
    "Washington", "Tennessee", "Seattle", "San Francisco", "San Diego",
    "Pittsburgh", "Philadelphia", "New York", "New Orleans", "New England",
    "Newark", "Minnesota", "Miami", "Los Angeles", "Las Vegas", "Kansas City",
    "Jacksonville", "Indianapolis", "Houston", "Green Bay", "Detroit",
    "Denver", "Dallas", "Cleveland", "Cincinnati", "Chicago", "Charlotte",
    "Buffalo", "Baltimore", "Atlanta", "Arizona"
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
    def __init__(self, coach: discord.Member, team_name: str, guild: discord.Guild, *, timeout=180):
        super().__init__(timeout=timeout)
        self.coach = coach
        self.team_name = team_name
        self.guild = guild

    @button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
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
        except Exception as e:
            await interaction.followup.send(f"❌ Something went wrong: `{e}`", ephemeral=True)
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

        fo = None
        fo_role = discord.utils.get(guild.roles, name="Franchise Owner")
        if fo_role and team_role:
            for m in fo_role.members:
                if team_role in m.roles:
                    fo = m
                    break

        if fo:
            try:
                embed = discord.Embed(
                    title="UFFL - Demand Alert",
                    description=f"{member.mention} has demanded a release from **{self.team_name}**.",
                    color=discord.Color.orange()
                )
                await fo.send(embed=embed)
            except discord.Forbidden:
                print(f"Could not DM FO {fo.display_name}")

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
        self.synced = False

    async def setup_hook(self):
        if self.synced:
            return
        self.synced = True

        try:
            print("🧨 Force-wiping ALL GLOBAL AND GUILD COMMANDS...")

            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            guild = discord.Object(id=GUILD_ID)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)

            print("✅ All global and guild commands wiped and re-synced.")

            global_cmds = await self.tree.fetch_commands()
            guild_cmds = await self.tree.fetch_commands(guild=guild)
            print("🌐 Global commands:", [cmd.name for cmd in global_cmds])
            print("🏠 Guild commands:", [cmd.name for cmd in guild_cmds])

        except Exception as e:
            print(f"❌ setup_hook error: {e}")
            raise e

# ✅ Moved bot instantiation up so decorators can reference it
bot = FootballFusionBot()



@bot.event
async def on_application_command_error(interaction, error):
    print(f"Command error: {error}")


@bot.tree.command(name="offer", description="Offer a player to join your team.")
@app_commands.describe(target="The user to offer a spot on your team.")
async def offer(interaction: discord.Interaction, target: discord.Member):
    await interaction.response.defer(ephemeral=True)

    allowed_roles = {"Franchise Owner", "General Manager"}  # 👈 edit this as needed
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
        return


    if "Franchise Owner" not in [r.name for r in interaction.user.roles]:
        await interaction.followup.send("Only Franchise Owners can offer players.", ephemeral=True)
        return

    team_name = get_user_team(interaction.user)
    if not team_name:
        await interaction.followup.send("I couldn't figure out your team. Make sure you have a team role matching your team name.", ephemeral=True)
        return

    embed = discord.Embed(
        title="UFFL - Team Invite",
        description="Offer Received",
        color=discord.Color.blue()
    )
    embed.add_field(name="\u200B", value=f"**{team_name}** has offered you in UFFL!", inline=False)
    embed.add_field(name="Coach:", value=interaction.user.mention, inline=True)

    view = OfferView(coach=interaction.user, team_name=team_name, guild=interaction.guild)

    try:
        await target.send(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.followup.send("That user's DMs are closed.", ephemeral=True)
        return
    except Exception as e:
        await interaction.followup.send(f"Unexpected error: {e}", ephemeral=True)
        return

    await interaction.followup.send(f"Offer sent to {target.display_name} from **{team_name}**.", ephemeral=True)

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

    if team_role not in target.roles:
        await interaction.response.send_message(
            f"{target.display_name} is not on your team.",
            ephemeral=True
        )
        return

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

    embed = discord.Embed(
        title="UFFL - Release Notice",
        description="You have been released from your team.",
        color=discord.Color.red()
    )
    embed.add_field(name="Team:", value=team_name, inline=True)
    embed.add_field(name="Coach:", value=interaction.user.mention, inline=True)
    embed.set_footer(text="Thank you for your time. You are now a free agent.")

    try:
        await target.send(embed=embed)
        print(f"✅ Sent release DM to {target.display_name}")
    except discord.Forbidden:
        print(f"❌ Could not DM {target.display_name} — DMs may be closed.")
    except Exception as e:
        print(f"❌ DM send failed for {target.display_name}: {e}")

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
    allowed_roles = {"WORKERS", "Founder", "Franchise Owner"}
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

    embed = discord.Embed(
        title="UFFL Team Roster",
        description="Franchise Owners and their complete team lineups",
        color=discord.Color.teal()
    )

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

        embed.add_field(
            name=f"🏈 {team_name} — {total_members} member{'s' if total_members != 1 else ''}",
            value=team_list,
            inline=False
        )

    try:
        await interaction.user.send(embed=embed)
        await interaction.followup.send("📬 Sorted roster sent to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Could not send DM. Please make sure your DMs are open.", ephemeral=True)


@bot.tree.command(name="deadline_reminder", description="DM all Franchise Owners a deadline reminder.")
@app_commands.describe(deadline="Enter the deadline (e.g. April 20th at 11:59PM EST)")
async def deadline_reminder(interaction: discord.Interaction, deadline: str):
    allowed_roles = {"Founder", "WORKERS"}
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

@bot.tree.command(name="game_thread", description="Create a game thread between two teams. Automatically invites FOs, GMs, HCs, and staff.")
@app_commands.describe(team1="First team", team2="Second team")
async def game_thread(interaction: discord.Interaction, team1: str, team2: str):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    channel = interaction.channel
    thread_name = f"{team1} vs {team2}"

    team_roles = [discord.utils.get(guild.roles, name=team1), discord.utils.get(guild.roles, name=team2)]
    if None in team_roles:
        await interaction.followup.send("❌ One or both team roles could not be found.", ephemeral=True)
        return

    ranking_roles = {"Franchise Owner", "General Manager", "Head Coach"}
    staff_roles = {"Founder", "WORKERS"}

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
            auto_archive_duration=1440
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



from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "UFFL Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

import os
bot.run(os.environ["DISCORD_TOKEN"])
