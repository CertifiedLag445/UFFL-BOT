@bot.tree.command(name="botcmds", description="DMs you a list of all bot commands and how they work.")
async def botcmds(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # Acknowledge the command immediately

    command_guide = """
/OFFER
Send a team invite to a free agent.
    - Only Franchise Owners and General Managers can use it
    - Automatically detects which team the sender is on
    - Sends a DM to the selected user with Accept / Decline buttons
    - If Accepted:
        ~ Adds the team role
        ~ Removes the "Free agents" role
    - If Declined, the process ends silently
    - If offer was sent by a GM, the FO is notified privately via DM

/RELEASE
Remove a player from your team.
    - Only Franchise Owners and General Managers can use it
    - Target must have the same team role as the sender
    - Removes:
        ~ The team role
        ~ GM and HC roles (if applicable)
    - Adds the "Free agents" role
    - Sends the released user a DM with a farewell message
    - If released by a GM, the FO is notified privately

/DEMAND
Allows a player to request release from their current team.
    - Only usable by non-Franchise Owners
    - If an FO tries to use it, they're prompted to transfer FO first
    - Displays a confirmation prompt
    - If confirmed:
        ~ Removes team role
        ~ Adds the "Free agents" role
        ~ Sends a DM alerting the FO of the demand

/PROMOTE
Promote a teammate to HC, GM, or transfer FO role.
    - Only Franchise Owners can use it
    - Both the FO and the target must be on the same team
    - Grants the selected role (Head Coach, General Manager, or Franchise Owner)
    - Sends a DM to the promoted user
    - If promoting to FO:
        ~ A confirmation prompt appears
        ~ If confirmed:
            ~~ Transfers FO role
            ~~ Old FO stays on the team
            ~~ Both old and new FOs get a DM notification

/DEMOTE
Demote a teammate from HC or GM.
    - Only Franchise Owners can use it
    - FO and target must be on the same team
    - Removes the selected role
    - Sends a DM to the demoted user
    - Target still keeps their team role

/ROSTER
Get a full view of Franchise Owners and team rosters.
    - Only available to users with the WORKERS, Founder, or Franchise Owner role
    - Sends a private DM to the user
    - Lists all teams with:
        ~ Franchise Owner
        ~ GM / HC role tags for other players
        ~ Member counts
        ~ Discord user IDs

/DEADLINE_REMINDER
Notify all Franchise Owners about a deadline.
    - Only available to WORKERS or Founder
    - Sends a DM to each FO with the deadline info
    - Reports back how many DMs were successfully sent

/DEBUGCHECK
Simple test command to confirm if slash commands are active.
    - Available to any user
    - Sends a quick ephemeral “slash commands are live” message

/GAME_THREAD
Create a private thread for a scheduled game.
    - Only WORKERS and Founders can use it
    - Automatically adds:
        ~ FO, GM, and HC from both teams
        ~ WORKERS and Founder roles
    - The thread:
        ~ Is private
        ~ Named after the matchup (Team1 vs Team2)
        ~ Starts with a kickoff message

/DISBAND
Disband an entire team.
    - Only available to WORKERS or Founder
    - User selects a team from a dropdown
    - User enters a reason for disbanding
    - What happens next:
        ~ All members of that team have their roles wiped (team + GM/HC/FO)
        ~ Free agents role is added to all affected users
        ~ If any affected member was a GM or FO, they receive a DM with:
            ~~ Team name
            ~~ Reason for disbandment
            ~~ Timestamp (in EST)
            ~~ The name of the user who disbanded the team
    - Final report is sent back to the command user

/GAMETIME
Announce a scheduled game to a specific announcement channel (#⏳▕▏𝘎𝘈𝘔𝘌𝘛𝘐𝘔𝘌).
    - Only available to Franchise Owners, WORKERS, or Founder
    - Takes 4 inputs:
        ~ team1: team name (autocomplete)
        ~ team2: team name (autocomplete)
        ~ time_est: human-readable EST game time
        ~ private_server_link: a Discord invite or private match link
    - Bot searches each team for the Franchise Owner
    - Sends a formatted embed to the announcement channel, including:
        ~ Match title
        ~ FO mentions
        ~ Kickoff time (EST)
        ~ A clickable Join Here! link
"""

    try:
        await interaction.user.send(command_guide)
        await interaction.followup.send("📬 Command list sent to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Could not send DM. Please make sure your DMs are open.", ephemeral=True)
