#!/usr/bin/python3
#
# cambot - A telegram bot to get shots, videos and mqtt notifications
#          from yi-hack webcams.
# Copyright (C) 2021 Peter Kästle <peter |at| piie.net>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
cambot
"""

import logging
import subprocess
import urllib.request
import paho.mqtt.client as mqtt
import os.path
import argparse
import sys
import configparser

from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler

FFMPEG = "/usr/bin/ffmpeg"
FFMPEG_ARGS = " -loglevel warning "
TMP_DIR = "."
CAM_HOST=""
BOT_TOKEN = ""
MQTT_USER = ""
MQTT_PW = ""
MQTT_HOST = ""
MQTT_PORT = 1883
MQTT_SUBSCRIBE = ""
bot = None
allowed_users = []


#############################
# logging
#############################

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)


#############################
# ffmpeg handling
#############################

def rec(duration) -> bool:
    global ignore_events
    global FFMPEG
    global TMP_DIR
    global CAM_HOST
    ignore_events = 1
    ret = subprocess.call(FFMPEG + FFMPEG_ARGS + " -y -i rtsp://" + CAM_HOST + "/ch0_1.h264 -t 00:00:" +
            duration + " -vcodec copy " + TMP_DIR + "/camvid.mp4", shell=True)
    ignore_events = 0
    return ret

#############################
# user management
#############################
class user:
    id = None
    username = None
    notification = 0
    def __init__(self, id, username, notification):
        self.id = id
        self.username = username
        self.notification = notification
    def check(self, id):
        if self.id == id:
            return 1
        else:
            return 0
    def print(self):
        logging.info("allowed user: %s %s - notification: %d", self.id, self.username, self.notification)


def check_user(update, caller) -> bool:
    """show user info and check whether user is in allowed list"""
    user = update.effective_user
    logging.info('got "%s" call from %s - %s', caller, user.id, user.username)
    for u in allowed_users:
        if u.check(user.id):
            return 1
    logging.info('user %s - %s  not in allowed list', user.id, user.username)
    return 0


#############################
# mqtt
#############################
# The callback for when the client receives a CONNACK response from the server.
def on_mqtt_connect(client, userdata, flags, rc):
    global MQTT_SUBSCRIBE
    logging.info("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(MQTT_SUBSCRIBE + "/motion")
    client.subscribe(MQTT_SUBSCRIBE + "/sound")

ignore_first_sound = 1
ignore_events = 0

# The callback for when a PUBLISH message is received from the server.
def on_mqtt_message(client, userdata, msg):
    global bot
    global TMP_DIR
    global ignore_first_sound
    global ignore_events
    notifications = 0
    payload=str(msg.payload.decode("utf-8"))
    logging.info(msg.topic+" |"+payload+"| - ignore %d - ignore-sound %d", ignore_events, ignore_first_sound)
    for u in allowed_users:
        if u.notification:
            notifications = 1
    if notifications and bot and ignore_events == 0:
        if payload == "sound":
            if ignore_first_sound:
                ignore_first_sound = 0
            else:
                if rec("03") == 0:
                    for u in allowed_users:
                        if u.notification:
                            logging.info("sending sound event to %s", u.username)
                            bot.send_video(chat_id=u.id, caption="sound event",
                                    video=open(TMP_DIR + "/camvid.mp4", 'rb'), reply_markup=reply_markup)

        if payload == "motion_start":
            if rec("03") == 0:
                for u in allowed_users:
                    if u.notification:
                        logging.info("sending motion event to %s", u.username)
                        bot.send_video(chat_id=u.id, caption="motion event",
                                video=open(TMP_DIR + "/camvid.mp4", 'rb'), reply_markup=reply_markup)


#############################
# telegram
#############################
keyboard = [
    [
        InlineKeyboardButton("Meldungen AN", callback_data='notifyon'),
        InlineKeyboardButton("Meldungen AUS", callback_data='notifyoff'),
    ],
    [
        InlineKeyboardButton("Bild", callback_data='shot'),
        InlineKeyboardButton("Video (1s)", callback_data='video1'),
        InlineKeyboardButton("Video (5s)", callback_data='video5'),
    ],
]
reply_markup = InlineKeyboardMarkup(keyboard)

# Define a few command handlers. These usually take the two arguments update and
# context.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    if not check_user(update, "start"):
        return
    update.message.reply_text('Wa widd?', reply_markup=reply_markup)

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    if not check_user(update, "help_command"):
        return
    update.message.reply_text('Help!')

def echo(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    if not check_user(update, "echo"):
        return
    update.message.reply_text(update.message.text)


# Button handler
def button(update: Update, context: CallbackContext) -> None:
    global TMP_DIR
    """Parses the CallbackQuery and updates the message text."""
    if not check_user(update, "button"):
        return
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()
    if query.data == "notifyon":
        for u in allowed_users:
            if u.check(update.effective_user.id):
                query.bot.send_message(chat_id=query.message.chat_id, text='Meldungen sind jetzt AN',
                        reply_markup=reply_markup)
                u.notification = 1
        for u in allowed_users:
            u.print()
    elif query.data == "notifyoff":
        for u in allowed_users:
            if u.check(update.effective_user.id):
                query.bot.send_message(chat_id=query.message.chat_id, text='Meldungen sind jetzt AUS',
                        reply_markup=reply_markup)
                u.notification = 0
        for u in allowed_users:
            u.print()
    elif query.data == "shot":
        query.bot.send_message(chat_id=query.message.chat_id, text='Bild kommt...')
        urllib.request.urlretrieve("http://" + CAM_HOST + ":8080/cgi-bin/snapshot.sh?res=high&watermark=yes",
                TMP_DIR + "/cambotshot.jpg")
        query.bot.send_photo(chat_id=query.message.chat_id, photo=open(TMP_DIR + "/cambotshot.jpg", 'rb'),
                reply_markup=reply_markup)
    elif query.data == "video1":
        query.bot.send_message(chat_id=query.message.chat_id, text='Video kommt...')
        if rec("01") == 0:
            query.bot.send_video(chat_id=query.message.chat_id, video=open(TMP_DIR + "/camvid.mp4", 'rb'),
                reply_markup=reply_markup)
    elif query.data == "video5":
        query.bot.send_message(chat_id=query.message.chat_id, text='Video kommt...')
        if rec("05") == 0:
            query.bot.send_video(chat_id=query.message.chat_id, video=open(TMP_DIR + "/camvid.mp4", 'rb'),
                reply_markup=reply_markup)


#############################
# main
#############################
def main() -> None:
    global FFMPEG
    global CAM_HOST
    global bot
    global TMP_DIR
    global BOT_TOKEN
    global MQTT_USER
    global MQTT_PW
    global MQTT_HOST
    global MQTT_PORT
    global MQTT_SUBSCRIBE
    global allowed_users

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')
    args = parser.parse_args()
    if not args.config:
        print("usage: " + sys.argv[0] + " -c config.ini")
        return
    print("loading config: " + args.config)
    config = configparser.ConfigParser()
    try:
        config.read(args.config)
        CAM_HOST = config.get("Camera", "host")
        TMP_DIR = config.get("config", "tmp_dir")
        BOT_TOKEN = config.get("Telegram", "token")
        MQTT_USER = config.get("MQTT", "user")
        MQTT_PW = config.get("MQTT", "pass")
        MQTT_HOST = config.get("MQTT", "host")
        MQTT_PORT = config.getint("MQTT", "port")
        MQTT_SUBSCRIBE = config.get("MQTT", "subs")

        for user_to_add in config['Telegram_Users']:
            print("adding user: " + user_to_add)
            tmp = user(config.getint("Telegram_Users", user_to_add), user_to_add, 0)
            allowed_users.append(tmp)

    except:
        print("cannot load config!")
        return


    # create tmp directory
    if not os.path.exists(TMP_DIR):
        os.makedirs(TMP_DIR)

    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    logging.info("CAM host %s", CAM_HOST)
    logging.info("ffmpeg: %s", FFMPEG)
    logging.info("Printing user list")
    for u in allowed_users:
        u.print()

    if not os.path.isfile(FFMPEG):
        FFMPEG = "/mnt/ffmpeg"
    logging.info("ffmpeg: %s", FFMPEG)

    mqtt_client = mqtt.Client()
    mqtt_client.username_pw_set(MQTT_USER, password=MQTT_PW)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()

    updater = Updater(BOT_TOKEN)
    bot = updater.bot

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CallbackQueryHandler(button))

    # on non command i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

    mqtt_client.loop_stop()

if __name__ == '__main__':
    main()

