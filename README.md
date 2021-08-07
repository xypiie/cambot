# cambot
A telegram bot to get shots, videos and mqtt notifications from yi-hack webcams.

## Installation
`pip install python-telegram-bot paho-mqtt`

## Configuration
Copy the `default_config.ini` and fill it with your informations.

## Running
`./cambot.py`

## Adding users
Whenever you write your bot a message and you're not in the list of allowed users,
you'll get a print like this:

`2021-08-07 16:27:38,995 - INFO - check_user - user <ID> - <USERNAME>  not in allowed list`

Just add the id + username accordingly into the config.
