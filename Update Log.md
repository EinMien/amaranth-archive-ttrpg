# Amaranth Archive v1.1 Update Logs
- Revamped editing your character sheet.
  - `/editsheet` lets you edit everything about your characters, including Base Stats (FIGHT, DODGE, and HP), EQUIPs, Ability, Chocolate Ratings, Trap & Race Stats (Dexterity, Cautiousness, Trap Quirk, Timer, and Race Whim), and MAGICs.
  - `/addmagic`, `/setstats`, `/setability`, `/setequips`, and `/chocs` removed due to being useless now.
- Added `/dmtargetscope` for Admins to restrict autocomplete options. Players are restricted to the default.
- Added `/joinparty` and `/leaveparty` for players to make their characters join and leave server parties.
- Added `/characterlist player` and `/characterlist party` to check a list of characters you own and in a server party.
- Made `/randomitem` and `/randomstatus` easier to use.
- Moved Cooldowns to under the effects of MAGICs.
- Allows you to use ITEMs on other Party Members instead of just yourself.
- Allows bulk ITEM movement between your Party Member and Storage.
- Automatically sorts inventories in alphabetical order.
- Added a 5000 Character cap per embed to comply with Discord's limits. (Character here means letters of a word and spaces, not your RP characters.)
- Add new `/help` boxes for newly made commands.
- Reworked the backend to make each server have their own list of characters. (Note: If 2 or more characters with the same exact name are created in a server, the bot will only detect whichever is first in the database.)
- You must use `/registercharacter` to transfer old characters to the new database.
- Fixed the issue where Ability won't finish if over 1024 characters. 
- Fixed Dark Chocolate Bar and Milk Chocolate Bar using the White Chocolate Ratings.
- Nerfed Fox.
- Other smaller updates.
(Note: Some commands may appear twice; this is a discord sync issue. Both commands will still work.)


# Amaranth Archive v1.2 Update Logs
- Added the ability to use multiple uses of one item at once. (Ex. If you have 3/10 uses of Sylna Cookies left, you can use all 3 at once.)
- Added the ability to add an ITEM with a partial amount of uses.
- Added `/clearinventory` so Admins can wipe the inventory of a character, an entire party, or their party's storage.
- Nerfed Fox.


# Amaranth Archive v1.3 Update Logs
- [Redacted, build broken].
- Nerfed Fox.


# Amaranth Archives v1.4 Update Logs
- Added a `view_only` field to `/storage`. Typing in `true` lets you see a list of the current storage.
- Added `/metronome` command so that the Handy Glove finally has a use. This command selects a random MAGIC from a select pool of 50.
- Added reroll buttons to `/randomitem` and `/randomstatus` to replace the rolled item with another one without needing to type the command again. `/metronome` also has this.
- Fixed a mistake where ITEMs from `/item` that have variants (Disliked, Well-Liked, or Obsessed) appeared in ephemeral/private messages. Now all ITEMs should appear as a normal message visible by everyone.
- Fixed a bug where `/movesheet` was able to incorrectly target a Party's Storage.
- Nerfed Fox.


# Amaranth Archives v1.5 Update Logs
- Added `Badge Group` option to `/creategroup`, `/editgroup`, and `/removegroup`, allowing users to create, edit, and delete a badge group.
- Added `/addbadge`, `/editbadge`, and `/removebadge` commands, which allows users to, well, you know what they do.
- Added a `Copy Format` button to `/badge` allowing users to quickly copy a pre-formatted name and effect input for character sheets.
- Fixed descriptions of the `Blizzard` metronome, and the `Wish Badge` badge.
- Fixed a bug where `/badge` displayed the next badge's name in the description.
- Added an `Edit MAGIC` button to `/editsheet` simplifying editing process. The `Add MAGIC` button can still edit a MAGIC because I was too lazy to rewrite the function.
- Fixed an issue where the `/creategroup` confirmation message had a speech impairment.
- Added a bug where I didn't wait for <@863657238416588810> to give me the text for the `/help` commands of the `/addbadge`, `/editbadge`, and `/removebadge` commands and just did my own thing.
- Updated `/backup` command to increment through every file in the bot's dataset instead of using a hard-coded list.
- Nerfed Fox.


# Amaranth Archive v1.6 Update Logs
- Added DMTargetScope Server, so the DM can target every character within their server.
- Added chunking to base stats and equips so the bot doesn't fail to send due to text limitations.
- Added pagination to all `/movesheet` fields so that if you hit the text limit, the bot will transfer the rest to a seperate page. (For example: If you make 6 MAGICs but only 4 fit within the limit, MAGIC 5 and 6 go into Page 2 and there will be buttons to scroll between pages.)
- Added the ability for a party to have multiple different storages.
- Added descriptions for `/addbadge`, `/editbadge`, and `/removebadge`.
- Purged a couple of unnecessary test characters.
- Nerfed Fox.


# Amaranth Archive v1.7 Update Logs
- Added the ability for the DM to remove parties.
- Added the ability to migrate movesheets from one server to the next.
- Fixed many small spelling mistakes and formatting with the `/badge` section of `/help`.
- Fixed an issue where `/movesheet` won't pull up movesheets from other servers.
- Nerfed Fox.