# ruff: noqa: E501
"""English strings (default language)."""

STRINGS: dict[str, str] = {
    "language_name": "🇬🇧 English",
    # --- war states and results ---
    "state_preparation": "🛡 Preparation day",
    "state_in_war": "⚔️ Battle day",
    "state_ended": "🏁 War ended",
    "state_not_in_war": "😴 Not in war",
    "result_win": "🏆 Victory!",
    "result_lose": "💀 Defeat",
    "result_tie": "🤝 Draw",
    # --- durations ---
    "dur_hm": "{h}h {m}m",
    "dur_h": "{h}h",
    "dur_m": "{m}m",
    # --- war summary ---
    "kind_war": "War",
    "kind_cwl": "CWL",
    "kind_cwl_round": "CWL, round {n}",
    "until_start": "⏳ Battle day starts in: <b>{time}</b>",
    "until_end": "⏳ War ends in: <b>{time}</b>",
    "score_attacks": "🗡 Attacks",
    "clan_attacks_left": "Attacks left in the clan: <b>{n}</b>",
    "member_left": " — {n} left",
    "all_attacked": "🎉 All attacks used!",
    "missed_title": "❗ Haven't attacked yet:",
    "missed_title_ended": "❗ Missed their attacks:",
    "missed_unlinked": "<i>Not linked to Telegram: {n}. Link with /link #TAG</i>",
    "prep_no_attacks": "It's preparation day — attacks aren't open yet.",
    # --- notifications ---
    "notify_prep": "🔎 <b>Opponent found!</b>\n{title}\n{timing}\n\nTime to check your war base and Clan Castle troops.",
    "notify_start": "🔥 <b>The war has started!</b>\n{title}\n{timing}",
    "notify_rules": "\n\n📌 <b>Clan rules:</b>\n{rules}",
    "notify_remind": "⏰ <b>{time} left in the war!</b>\n{title}\n\n{missed}",
    "notify_end_missed": "\n\n❗ Missed their attacks: {names}",
    "dm_remind_one": "⏰ <b>{name}</b>, you still have {n} attack!",
    "dm_remind_many": "⏰ <b>{name}</b>, you still have {n} attacks!",
    "dm_remind_body": "{title}\nWar ends in: <b>{time}</b>\n\n<i>Turn off personal reminders: /notify</i>",
    # --- CWL ---
    "cwl_header": "🏆 <b>Clan War League</b> · season {season} · round {n}/{total}",
    "cwl_table_title": "📊 <b>CWL standings</b> · season {season}",
    "cwl_table_note": "<i>Stars include +10 for each war win. Destruction is the total over all wars.</i>",
    # --- accounts ---
    "accounts_none": "You haven't linked any accounts yet.\n\nLink one: <code>/link #TAG</code>\nThe tag is in your in-game profile, right under your name.",
    "accounts_title": "👤 <b>Your accounts</b>",
    "acc_not_in_war": "    not in the current war",
    "acc_no_attacks": "    no attacks yet · {n} left",
    "acc_left": "    attacks left: {n}",
    "acc_unverified_hint": "<i>▫️ — not verified. To prove ownership: /link #TAG TOKEN (the token is in the game: Settings → More Settings → API Token).</i>",
    # --- help ---
    "help_group": (
        "<b>Clan Warden</b> keeps an eye on your clan wars and reminds players to attack.\n\n"
        "<b>War</b>\n"
        "/war — current war or CWL round\n"
        "/missed — who hasn't attacked yet\n"
        "/cwl — CWL round · /cwltable — group standings\n\n"
        "<b>Accounts</b>\n"
        "/link #TAG — link your game account\n"
        "/unlink #TAG — unlink it\n"
        "/me — my accounts and attacks\n"
        "/notify — personal reminders on/off\n\n"
        "<b>Group admins</b>\n"
        "/setclan #TAG — connect a clan to this group\n"
        "/settopic — work only in this topic\n"
        "/settings — notifications and reminders\n"
        "/setrules text — clan rules shown when a war starts\n"
        "/checklinks — clan members without a linked account\n"
        "/language — bot language\n\n"
        "/menu — the same with buttons"
    ),
    "help_private": (
        "👋 <b>Hi! I'm Clan Warden.</b>\n\n"
        "I watch Clash of Clans wars for your clan: I post to the clan group when a war starts, remind everyone a few hours before the end with a list of who hasn't attacked, and post the results. I can also remind you personally.\n\n"
        "<b>Getting started:</b>\n"
        "1. Add me to your clan's group.\n"
        "2. A group admin sends <code>/setclan #CLAN_TAG</code>.\n"
        "3. Every player sends <code>/link #PLAYER_TAG</code> so I can mention them in reminders.\n\n"
        "In private chat /war, /missed and /cwl use the clan of your linked account (or pass a tag: <code>/war #TAG</code>).\n\n"
        "/help — all commands · /language — change language"
    ),
    "group_welcome": (
        "👋 Hi everyone! I'll keep an eye on your clan wars.\n\n"
        "<b>Group admin:</b> connect your clan with <code>/setclan #CLAN_TAG</code>.\n"
        "If this group has topics, send /settopic in the topic I should use.\n\n"
        "<b>Players:</b> link your accounts with <code>/link #TAG</code> so I can ping you when you have attacks left.\n\n"
        "All commands: /help"
    ),
    "menu_prompt": "What would you like to see?",
    "private_fallback": "I don't know that command. Try /menu or /help.",
    # --- settings ---
    "settings_title": "⚙️ <b>Group settings</b>",
    "settings_clan": "Clan: {clan}",
    "settings_clan_none": "not connected (/setclan)",
    "settings_where": "Where I work: {where}",
    "settings_topic": "topic #{id}",
    "settings_whole_chat": "the whole chat",
    "opt_prep": "Opponent found",
    "opt_start": "War start",
    "opt_remind": "Reminder {h}h before the end",
    "opt_end": "War results",
    "opt_mentions": "Mention players in reminders",
    "settings_autodelete": "🧹 Auto-delete replies: {value}",
    "autodelete_off": "off",
    "autodelete_after": "after {n} min",
    "settings_rules": "📌 Rules: {value}",
    "rules_set": "set",
    "rules_none": "none",
    "settings_language": "🌐 Language: {value}",
    # --- buttons ---
    "btn_war": "⚔️ War",
    "btn_missed": "❗ Who hasn't attacked",
    "btn_cwl": "🏆 CWL",
    "btn_cwl_table": "📊 CWL standings",
    "btn_me": "👤 My accounts",
    "btn_settings": "⚙️ Settings",
    "btn_help": "❓ Help",
    "btn_refresh": "🔄 Refresh",
    "btn_menu": "« Menu",
    "btn_opt_remind": "Reminder",
    "btn_remind_hours": "⏰ {h}h before",
    "btn_mentions": "Player mentions",
    "btn_autodelete": "🧹 Auto-delete: {value}",
    "btn_language": "🌐 Language",
    "btn_unlink": "❌ {name} ({tag})",
    # --- errors ---
    "err_invalid_ip": "⚠️ The bot can't reach the game API: its API key doesn't allow this server's IP. Please tell the bot owner.",
    "err_private_log": "🔒 The clan's war log is private. A leader or co-leader can make it public: Clan → Edit → War log: Public.",
    "err_not_found": "🤷 Clan or player not found. Please check the tag.",
    "err_maintenance": "🛠 Clash of Clans is under maintenance. Please try again later.",
    "err_rate_limited": "🐢 Too many requests to the game API. Please try again in a minute.",
    "err_api": "😵 The game API isn't responding. Please try again later.",
    "err_bad_clan_tag": "Invalid clan tag. Example: <code>/war #2PP</code>",
    "err_no_clan": "No clan is connected to this group yet. An admin can do it: /setclan #TAG",
    "err_which_clan": "I'm not sure which clan you mean. Link your account (/link #TAG) or pass a clan tag: <code>/war #TAG</code>",
    # --- views ---
    "not_in_war_long": "😴 The clan isn't in a war right now. As soon as matchmaking or preparation starts, it'll show up here.",
    "not_in_war": "😴 The clan isn't in a war right now.",
    "not_in_cwl": "🏆 The clan isn't in the Clan War League right now.",
    "menu_outdated": "This menu is outdated, send /menu",
    "loading": "Loading…",
    "settings_admins_only": "Only group admins can change settings",
    # --- linking ---
    "link_usage": (
        "Usage: <code>/link #TAG</code>\n"
        "The tag is in your in-game profile, right under your name.\n\n"
        "To prove the account is yours: <code>/link #TAG TOKEN</code>, the token is in the game: "
        "Settings → More Settings → API Token. Better send the token to me in private."
    ),
    "link_bad_tag": "That tag doesn't look right. Tags only use the characters 0289PYLQGRJCUV.",
    "player_not_found": "Player <code>{tag}</code> not found.",
    "token_invalid": "❌ That token didn't work. Tokens expire after a few minutes — grab a new one in the game.",
    "link_taken": "<b>{name}</b> is already linked by someone else.\nIf it's your account, prove it: <code>/link #TAG TOKEN</code> (in private chat).",
    "link_limit": "You can link at most {n} accounts.",
    "link_done": "🔗 <b>{name}</b> (TH{th}){clan} {status}.",
    "link_from_clan": " from {clan}",
    "link_status_verified": "linked and ✅ verified",
    "link_status_linked": "linked",
    "link_dm_hint": "\n\nTo get personal reminders, send me /start in private chat.",
    "unlink_done": "🗑 <code>{tag}</code> unlinked.",
    "unlink_not_yours": "That tag isn't linked to you.",
    "no_links": "You don't have any linked accounts.",
    "unlink_choose": "Which account do you want to unlink?",
    "not_your_account": "That's not your account",
    "unlinked_toast": "Unlinked",
    "notify_on": "🔔 Personal reminders are on. I'll message you if you still have attacks near the end of a war.",
    "notify_on_group_hint": "\nDon't forget to send me /start in private — Telegram won't let me message you first.",
    "notify_off": "🔕 Personal reminders are off.",
    # --- admin ---
    "group_only": "This command works in the clan group.",
    "admins_only": "Only group admins can use this command.",
    "setclan_usage": "Usage: <code>/setclan #CLAN_TAG</code>",
    "setclan_done": (
        "✅ This group is now connected to <b>{name}</b> <code>{tag}</code> ({members} members).\n\n"
        "I'll post war start, reminders and results here. Configure: /settings\n"
        "Players — link your accounts: <code>/link #TAG</code>"
    ),
    "setclan_private_log": "\n\n⚠️ The clan's war log is private, so I can't see wars. Make it public in the clan settings.",
    "settopic_need_topic": "Send this command inside the topic where the bot should work.",
    "settopic_done": "✅ From now on I'll reply and post notifications only in this topic.",
    "unsettopic_done": "✅ I'll work in the whole chat now.",
    "rules_cleared": "Rules cleared.\nSet them: <code>/setrules First attack — mirror…</code> (multiple lines are fine)",
    "rules_too_long": "Too long — {n} characters max.",
    "rules_saved": "✅ Rules saved, I'll show them when a war starts:\n\n{rules}",
    "checklinks_need_clan": "Connect a clan first: /setclan #TAG",
    "checklinks_title": "🔗 <b>Linked accounts in {clan}</b>",
    "checklinks_count": "Linked: {linked} of {total}",
    "checklinks_missing": "\nNot linked:",
    "checklinks_hint": "\nEveryone can link themselves: <code>/link #TAG</code>",
    "checklinks_all": "\n🎉 Every member has linked their account.",
    # --- language ---
    "language_choose": "Choose the bot language:",
    "language_set": "✅ Language: {name}",
    # --- bot command descriptions ---
    "cmd_menu": "Menu",
    "cmd_me": "My accounts and attacks",
    "cmd_war": "Current war",
    "cmd_missed": "Who hasn't attacked",
    "cmd_cwl": "Clan War League round",
    "cmd_cwltable": "CWL standings",
    "cmd_link": "Link an account: /link #TAG",
    "cmd_unlink": "Unlink an account",
    "cmd_notify": "Personal reminders on/off",
    "cmd_settings": "Settings (admins)",
    "cmd_language": "Language",
    "cmd_help": "Help",
}
