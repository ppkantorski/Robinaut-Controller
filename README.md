# Robinaut-Controller
Freqtrade Telegram Helper Bot

# Features
Besides the commands below, this bot can also plot live when orders are placed on your bot.
```
/help_control - default help page
/plot - plot pairs for specified bot
/indicators - obtain indicator values for desired pairs (still beta, needs work)
/public_url - obtain local NGROK tunnels for bots
/sync_configs - (something i'm playing with to sync data.  may not be useful for you right now.)
```
# How to use

1.  Place the files in the directory above the folder containing 'user_data'.  Name the folder according to the bot name.
/ft_bots/ft_bot_1/user_data
/ft_bots/ft_bot_2/user_data
...
/ft_bots/rbn_controller.py
/ft_bots/rbn_controller.json
/ft_bots/rbn_controller_launcer.zsh

2. Add in your configurations into the .json.
3. When working with Telegram, be sure to create a group for your Freqtrade bot.  This group will contain you, your Freqtrade bot, and the controller bot.  Use the same group chat id for both bots.  Make sure that the bots are set to "admin" privileges, that you are set to "anonymous", and that history is set to be logged.
