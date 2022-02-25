#!/usr/bin/env python3.
import telegram#, emoji
from telegram.ext.updater import Updater
from telegram.update import Update
from telegram.ext.callbackcontext import CallbackContext
from telegram.ext.commandhandler import CommandHandler
from telegram.ext.messagehandler import MessageHandler
from telegram.ext.filters import Filters
from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import threading
import ast
import os, sys
import pandas as pd
import pprint
import psutil
import pytz
import time
import datetime as dt
import json
import sqlite3
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw 
from pymemcache.client import base
memcache_client = base.Client(('localhost', 11211))

# Define script path
script_path = os.path.dirname(os.path.abspath( __file__ ))
os.chdir(script_path); sys.path.append(script_path)
from pathlib import Path # for home path

import mplfinance as mpf
import matplotlib
import matplotlib.dates as mdates
from matplotlib import pyplot as plt

# Change pyplot behavior for no-gui usage
plt.switch_backend('Agg')
plt.style.use('ggplot')



# load controller configurations
with open(f'{script_path}/rbn_controller.json', 'r') as json_file:
    controller_cfg = json.load(json_file)


# For making object run in background
def background_thread(target, args_list):
    args = ()
    for i in range(len(args_list)):
        args = args + (args_list[i],)
    pr = threading.Thread(target=target, args=args)
    pr.daemon = True
    pr.start()
    return pr

def cached_str_eval(entry):
    #print(entry)
    entry = entry.decode('utf-8')
    try:
        entry = ast.literal_eval(entry)
    except:
        pass
    return entry

class RobinautController(object):
    def __init__(self):
        # List of ft_bots within the ft_bots directory (must not include a '-' character)
        self.ft_bots = controller_cfg['bot_names']
        
        # Database settings
        self.db_files = ['tradesv3.sqlite', 'tradesv3.dryrun.sqlite']
        self.sql_client = SQLClient()
        self.timezone =  pytz.timezone(zone=controller_cfg['plot']['timezone'])
        
        # Telegram settings
        self.token = controller_cfg['telegram']['token']
        self.chat_id = controller_cfg['telegram']['chat_id']
        self.admin = controller_cfg['telegram']['admin']
        self.user_list = controller_cfg['telegram']['user_list']
        
        print(self.admin)
        
        self.bot = telegram.Bot(token=self.token)
        self.updater = Updater(token=self.token, use_context=True)
        self.admin_filter = (Filters.user(username=self.admin))
        self.user_filter = (Filters.user(username=self.admin))#Filters.chat(int(self.chat_id))#
        self.group_filter = (Filters.sender_chat(int(self.chat_id)))
        
        # Load freqtrade configurations jsons
        self.pairs = {}
        self.configs = {}
        self.strategies = {}
        for ft_bot in self.ft_bots:
            with open(f'{script_path}/{ft_bot}/user_data/config.json', 'r') as json_file:
                self.configs[ft_bot] = json.load(json_file)
                pair_whitelist = self.configs[ft_bot]['exchange']['pair_whitelist']
                pair_blacklist = self.configs[ft_bot]['exchange']['pair_blacklist']
                self.pairs[ft_bot] = list(set(pair_whitelist).union(set(pair_blacklist)) - set(pair_blacklist))
                self.pairs[ft_bot].sort()
                self.strategies[ft_bot] = self.configs[ft_bot]['strategy']
        
        
        # Execute background order plot updates
        background_thread(self.order_alert_plots, [])
    
    
    # Background thread for checking the sqlite3 database and plotting new entries
    def order_alert_plots(self):
        TIMEOUT = 5
        MAX_ENTRIES = 50
        table = 'orders'
        query = f"SELECT * FROM {table} ORDER BY id DESC LIMIT {MAX_ENTRIES};"
        
        modifications_log = {}
        id_set_log = {}
        
        loop_counter = 0
        while True:
            for ft_bot in self.ft_bots:
                for db_file in self.db_files:
                    db_file_path = f'{script_path}/{ft_bot}/user_data/{db_file}'
                    if os.path.exists(db_file_path) == False:
                        continue
                    
                    tmp_db_file = db_file.replace('tradesv3', '.tmp')
                    tmp_db_file_path = f'{script_path}/{ft_bot}/user_data/{tmp_db_file}'
                    
                    if loop_counter == 0:
                        os.system(f'cp {db_file_path} {tmp_db_file_path}')
                        records = self.sql_client.load_many(query, tmp_db_file_path)
                        column_names = self.sql_client.get_column_names(table, tmp_db_file_path)
                        os.system(f'rm -rf {tmp_db_file_path}')
                        records = pd.DataFrame(records, columns=column_names)
                        id_records = records['id']
                        
                        #id_records = [records[i][0] for i in range(len(records))]
                        #print(id_records)
                        id_set_log[f'{ft_bot}_{db_file}'] = set(id_records)
                    
                    last_mtime = os.path.getmtime(db_file_path)
                    if f'{ft_bot}_{db_file}' in modifications_log.keys() and last_mtime > modifications_log[f'{ft_bot}_{db_file}']:
                        os.system(f'cp {db_file_path} {tmp_db_file_path}')
                        records = self.sql_client.load_many(query, tmp_db_file_path)
                        column_names = self.sql_client.get_column_names(table, tmp_db_file_path)
                        os.system(f'rm -rf {tmp_db_file_path}')
                        records = pd.DataFrame(records, columns=column_names)
                        id_records = records['id']
                        pair_records = records['ft_pair']
                        side_records = records['ft_order_side']
                        
                        #id_records = [records[i][0] for i in range(len(records))]
                        #pair_records = [str(records[i][3]) for i in range(len(records))]
                        #id_pair_records = {}
                        #for i in range(len(id_records)):
                        #    id_record = id_records[i]
                        #    pair_record = pair_records[i]
                        #    id_pair_records[id_record] = pair_record
                        
                        id_set = set(id_records).union(id_set_log[f'{ft_bot}_{db_file}']) - id_set_log[f'{ft_bot}_{db_file}']
                        for id_entry in list(id_set):
                            #id_entry = list(id_set)[i]
                            current_record = records.loc[records['id'] == id_entry]
                            print(current_record)
                            pair = current_record['ft_pair'].iloc[0]
                            side = current_record['ft_order_side'].iloc[0]
                            price = current_record['price'].iloc[0]
                            order_date = current_record['order_date'].iloc[0]
                            print(pair)
                            print(side)
                            if 'dryrun' in db_file:
                                run_type = 'Dry Run'
                            else:
                                run_type = 'Live'
                            #pair = id_pair_records[id_entry]
                            print('ft_bot, pair, side, run_type')
                            print(f'{ft_bot}, {pair}, {side}, {run_type}')
                            self.plot_data(ft_bot, pair, current_record)
                            
                            #sad_sticker_file = f"{script_path}/{ft_bot}/stickers/sad.tgs"
                            #self.bot.send_photo(self.chat_id, open(sad_sticker_file,'rb'))
                            
                        id_set_log[f'{ft_bot}_{db_file}'] = set(id_records)
                    
                    modifications_log[f'{ft_bot}_{db_file}'] = last_mtime
            loop_counter += 1
            time.sleep(TIMEOUT)
    
    def test(self, update: Update, context: CallbackContext):
        #sad_sticker_file = f"{script_path}/ft_bot_2/stickers/sad.tgs"
        #self.bot.send_photo(self.chat_id, open(sad_sticker_file,'rb'))
        pass
    
    def start(self, update: Update, context: CallbackContext):
        update.message.reply_text(
            f"Welcome to the Robinaut Controller Bot.\nPlease type /help_control to see the commands available.")
    
    def help_control(self, update: Update, context: CallbackContext):
        update.message.reply_text("Available Commands :\n" +\
            "- /sync_configs - Sync configurations for all users. (admin only)\n" +\
            "- /indicators - Latest values for specified pair.\n" +\
            "- /plot - Get latest plot for specified pair.\n" +\
            "- /public_url - Get ngrok HTTPS tunnels.")
    
    def plot_data(self, ft_bot, pair, record=''):
        
        #update.message.reply_text("Config sync for all servers has been executed.")
        
        if len(record) > 0:
            side = record['ft_order_side'].iloc[0]
            price = record['price'].iloc[0]
            order_date = record['order_date'].iloc[0]
        else:
            side = ''
        
        # load memcache client
        pair_str = str(pair).replace('/', '_')
        #print(pair, pair_str)
        
        dataset = {}
        dataframe_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        
        try:
            indicators = controller_cfg['plot'][ft_bot]['indicators']
            if len(indicators) > 0:
                dataframe_columns += indicators
        except Exception as e:
            print(e)
        
        for column in dataframe_columns:
            #print(f'{ft_bot}_{pair_str}_{column}')
            try:
                dataset[column] = cached_str_eval(memcache_client.get(f'{ft_bot}_{pair_str}_{column}'))
            except Exception as e:
                print(e)
        dataframe = pd.DataFrame(dataset)
        #print(dataframe)
        
        live_plot_dir = f"{script_path}/{ft_bot}/live_plots"
        # If live plot folder doesn't exist, create it.
        if not os.path.isdir(live_plot_dir):
            os.makedirs(live_plot_dir)
        
        plot_file = f"{live_plot_dir}/{pair_str}_live.png"
        self.plot_dataframe(ft_bot, pair, dataframe, plot_file, record)
        #background_thread(plot_dataframe, [ft_bot, pair, dataframe])
        img = Image.open(plot_file)
        width, height = img.size
        draw = ImageDraw.Draw(img)
        # font = ImageFont.truetype(<font-file>, <font-size>)
        font = ImageFont.truetype(f"{script_path}/Helvetica.ttf", 16)
        #font = ImageFont.truetype("arial", 16)
        # draw.text((x, y),"Sample Text",(r,g,b))
        timestamp = str(dt.datetime.now(dt.timezone.utc).astimezone(self.timezone))
        text = f"{timestamp}"
        draw.text((20, height-30),text,(255,255,255),font=font)
        text = f'{self.admin}'
        draw.text((width-20-len(text)*9, height-30),text,(255,255,255),font=font)
        #if len(run_type) > 0:
        #    text = f'{run_type}'
        #    draw.text((width-20-len(text)*9, height-30),text,(255,255,255),font=font)
        img.save(plot_file)
        
        self.bot.send_photo(self.chat_id, open(plot_file,'rb'))
        
        #update.message.reply_text()
    
    def plot_dataframe(self, ft_bot, pair, dataframe, plot_file, record=''):
        #dataframe.date = pd.to_datetime(dataframe.date)
        
        if len(record) > 0:
            side = record['ft_order_side'].iloc[0]
            price = record['price'].iloc[0]
            order_date = record['order_date'].iloc[0]
        else:
            side = ''
            price = None
            order_date = None
        
        print(dataframe.columns)
        dataframe['date'] = pd.to_datetime(dataframe['date']).dt.tz_localize(tz=pytz.UTC)
        dataframe['date'] = pd.to_datetime(dataframe['date']).dt.tz_convert(tz=self.timezone)
        
        dataframe.set_index('date', inplace=True)
        
        
        indicators = controller_cfg['plot'][ft_bot]['indicators']
        indicator_colors = controller_cfg['plot'][ft_bot]['indicator_colors']
        
        apds = []
        for i in range(len(indicators)):
            indicator = indicators[i]
            indicator_color = indicator_colors[i]
            try:
                apds.append(mpf.make_addplot(dataframe[indicator], color=indicator_color))
            except:
                pass
        '''
        apds = [
            mpf.make_addplot(dataframe['sar_1'], color='green'),
            mpf.make_addplot(dataframe['sar_2'], color='yellow'),
            mpf.make_addplot(dataframe['ema_1'], color='red'),
        ]
        '''
        
        ohlc_df = dataframe.copy()
        ohlc_df.drop(indicators, axis=1)
        
        
        
        pair_str = pair.replace('/', '_')
        stake_currency = pair_str.split('_')[1]
        
        #plot_title = str(timestamp)+f"  -  {pair}\n"+self.strategy
        plot_title = f"\n\n{self.strategies[ft_bot]} - {pair}"
        
        #plt.gca().xaxis.set_major_formatter(dtFmt) # apply the format to the desired axis
        if len(side) > 0:
            side = side.capitalize()
            plot_title += f' - {side} Order'
        fig, axlist = mpf.plot(ohlc_df, addplot=apds, title=plot_title, ylabel=stake_currency, ylabel_lower='Volume', datetime_format='%H:%M', type='candle', style='nightclouds', volume=True, returnfig=True)
        #if stake_currency == 'USD':
        #    stake_char = $
        #axlist[0].yaxis.set_major_formatter(FormatStrFormatter('$%.2f'))
        plt.savefig(plot_file)
    
    
    
    def indicators(self, update: Update, context: CallbackContext):
        
        ft_bot = 'ft_bot_2'
        pair = 'DOGE/USD'
        pair = pair.replace('/', '_')
        
        text = ''
        dataset = {}
        last_entries = {}
        dataframe_columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'ema_1', 'sar_1', 'sar_2']
        for i in range(len(dataframe_columns)):
            column = dataframe_columns[i]
            dataset[column] = cached_str_eval(memcache_client.get(f'{ft_bot}_{pair}_{column}'))
            last_entries[column] = dataset[column][-1]
            if column not in ['date', 'volume']:
                last_entries[column] = '$'+str(round(last_entries[column], 4))
            text += f'*{column}:* `{last_entries[column]}`'
            if i != len(dataframe_columns)-1:
                text += '\n'
        #text='<b>Example message</b>', 
        
        
        #text = pprint.pformat(last_entries, indent=0, sort_dicts=False).replace("{","").replace("}","").replace("',","`").replace("':",":*").replace("'","`")
        print(text)
        update.message.reply_text(text, parse_mode=telegram.ParseMode.MARKDOWN)
    
    def sync_configs(self, update: Update, context: CallbackContext):
        os.system(f"python3 {script_path}/sync_configs.py")
        update.message.reply_text("Config sync for all servers has been executed.")
    
    
    def public_url(self, update: Update, context: CallbackContext):
        ngrok_tunnel_dict = os.popen('curl  http://localhost:4040/api/tunnels').read()
        ngrok_tunnel_dict = json.loads(ngrok_tunnel_dict)
        tunnels = ngrok_tunnel_dict['tunnels']
        
        try:
            text = ''
            tunnel_response = {}
            for i in range(len(tunnels)):
                tunnel = tunnels[i]
                name = tunnel['name']
                public_url = tunnel['public_url']
                tunnel_response[name] = public_url
                if name in self.ft_bots:
                    if len(text) != 0:
                        text += '\n'
                    text += f'{name}: {public_url}'
        except Exception as e:
            print(e)
            text = 'NGROK needs to be restarted.'
        
        print(text)
        update.message.reply_text(text)
    
    def unknown(self, update: Update, context: CallbackContext):
        pass
        #update.message.reply_text(
        #    "Sorry '%s' is not a valid command" % update.message.text)
    
    def unknown_text(self, update: Update, context: CallbackContext):
        pass
        #update.message.reply_text(
        #    "Sorry I can't recognize you , you said '%s'" % update.message.text)
    
    
    
    
    def plot(self, update: Update, context: CallbackContext):
        update.message.reply_text(self.plot_menu_message(), reply_markup=self.plot_menu_keyboard())
    
    def plot_menu(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        query.edit_message_text(text=self.plot_menu_message(), reply_markup=self.plot_menu_keyboard())
    
    def pair_plot_menu(self, update: Update, context: CallbackContext):
        #bot.callback_query.message.edit_text(self.first_plot_menu_message(), reply_markup=self.first_plot_menu_keyboard())
        #handle_str = str(update.callback_query.data)
        
        query = update.callback_query
        query.answer()
        
        query.edit_message_text(text=self.pair_plot_menu_message(), reply_markup=self.pair_plot_menu_keyboard())
        
    
    def plot_response(self, update: Update, context: CallbackContext):
        #bot.callback_query.message.edit_text(self.first_plot_menu_message(), reply_markup=self.first_plot_menu_keyboard())
        #self.plot_data(update, context)
        
        handle_str = str(update.callback_query.data)
        handle_str = handle_str.replace('_plot', '')
        split_str = handle_str.split('-')
        [ft_bot, pair] = split_str
        
        self.plot_data(ft_bot, pair)
        #requested_pair = update['callback_query']['message']['inline_keyboard'][0]['text']
        #print(requested_pair)
        #print('update')
        #print(update)
        #print(update.callback_query.data)
        #pprint.pprint(json.loads(update))
        #print('context')
        #print(context)
        query = update.callback_query
        query.answer()
        
        
        
    def plot_menu_message(self):
        return 'Choose the desired bot for plotting:'
    
    def pair_plot_menu_message(self):
        return 'Choose the desired pair for plotting:'
     
    def plot_menu_keyboard(self):
        keyboard = []
        
        for ft_bot in self.ft_bots:
            keyboard.append([InlineKeyboardButton(ft_bot, callback_data=f'{ft_bot}_plot_menu')])
        
        return InlineKeyboardMarkup(keyboard)
    
    def pair_plot_menu_keyboard(self):
        
        keyboard = []
        for ft_bot in self.ft_bots:
            if len(self.pairs[ft_bot]) <= 4:
                entries_per_row = 1
            elif len(self.pairs[ft_bot]) <= 8:
                entries_per_row = 2
            else:
                entries_per_row = 3
            for i in range(len(self.pairs[ft_bot])):
                pair = self.pairs[ft_bot][i]
                if i % entries_per_row == 0:
                    row = [InlineKeyboardButton(pair, callback_data=f'{ft_bot}-{pair}_plot')]
                elif i % entries_per_row != 0 and i != len(self.pairs[ft_bot])-1:
                    row.append(InlineKeyboardButton(pair, callback_data=f'{ft_bot}-{pair}_plot'))
                    #keyboard.append(row)
                if (i % entries_per_row == entries_per_row-1) or (i % entries_per_row != entries_per_row-1 and i == len(self.pairs[ft_bot])-1):
                    keyboard.append(row)
                
                #keyboard.append([InlineKeyboardButton(pair, callback_data=f'{ft_bot}-{pair}_plot')])
        keyboard.append([InlineKeyboardButton('Return to bot selection.', callback_data='plot_menu')])
        return InlineKeyboardMarkup(keyboard)
    
    # Start bot
    def deploy(self):
        self.updater.dispatcher.add_handler(CommandHandler('plot_data', self.plot_data, self.group_filter))
        self.updater.dispatcher.add_handler(CommandHandler('plot', self.plot, self.group_filter))
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.plot_menu, pattern='plot_menu'))
        for ft_bot in self.ft_bots:
            self.updater.dispatcher.add_handler(CallbackQueryHandler(self.pair_plot_menu, pattern=f'{ft_bot}_plot_menu'))
            for pair in self.pairs[ft_bot]:
                self.updater.dispatcher.add_handler(CallbackQueryHandler(self.plot_response, pattern=f'{ft_bot}-{pair}_plot'))
        #self.updater.dispatcher.add_handler(CallbackQueryHandler(self.second_submenu, pattern='m2_1'))
        self.updater.dispatcher.add_handler(CommandHandler('start', self.start, self.group_filter))
        self.updater.dispatcher.add_handler(CommandHandler('test', self.test, self.user_filter))
        self.updater.dispatcher.add_handler(CommandHandler('help_control', self.help_control, self.group_filter))
        #self.updater.dispatcher.add_handler(CommandHandler('plot', self.plot, self.user_filter))
        self.updater.dispatcher.add_handler(CommandHandler('indicators', self.indicators, self.group_filter))
        self.updater.dispatcher.add_handler(CommandHandler('public_url', self.public_url, self.group_filter))
        self.updater.dispatcher.add_handler(CommandHandler('sync_configs', self.sync_configs, self.group_filter))
        self.updater.dispatcher.add_handler(MessageHandler((Filters.text & self.group_filter), self.unknown))
        self.updater.dispatcher.add_handler(MessageHandler(
            (Filters.command & self.group_filter), self.unknown))  # Filters out unknown commands
        
        # Filters out unknown messages.
        self.updater.dispatcher.add_handler(MessageHandler((Filters.text & self.group_filter), self.unknown_text))
        
        self.updater.start_polling()

class SQLClient(object):
    def __init__(self):
        self.cnxn = None
        self.crsr = None
    
    def connect(self, db_file):
        # define the server and the database   
        try:
            self.cnxn = sqlite3.connect(db_file)
        except sqlite3.Error as e:
            print(e)
        self.crsr = self.cnxn.cursor()
    
    def insert(self, query, data_tuple, db_file): 
        # execute the query, commit the changes, and close the connection
        self.connect(db_file)
        self.crsr.execute(query, data_tuple)
        self.cnxn.commit()
        self.crsr.close()
        self.cnxn.close()
    
    def insert_many(self, query, data_tuple_list, db_file):
        
        # execute the query, commit the changes, and close the connection
        self.connect(db_file)
        self.crsr.executemany(query, data_tuple_list)
        self.cnxn.commit()
        self.crsr.close()
        self.cnxn.close()
    
    def load(self, query, db_file):
        
        self.connect(db_file)
        #self.crsr.execute(self.reset_cache_query)
        self.crsr.execute(query)
        record = self.crsr.fetchone()
        #self.cnxn.commit()
        self.crsr.close()
        self.cnxn.close()
        
        return record
    
    def load_many(self, query, db_file):
        
        self.connect(db_file)
        #self.crsr.execute(self.reset_cache_query)
        self.crsr.execute(query)
        records = self.crsr.fetchall()
        #self.cnxn.commit()
        self.crsr.close()
        self.cnxn.close()
        
        return records
    
    def get_column_names(self, table, db_file):
        query = f'select * from {table}'
        self.connect(db_file)
        self.crsr.execute(query)
        column_names = list(map(lambda x: x[0], self.crsr.description))
        self.crsr.close()
        self.cnxn.close()
        
        return column_names
        
    def close(self):
        self.crsr.close()
        self.cnxn.close()

def main():
    robinaut_controller = RobinautController()
    robinaut_controller.deploy()


if __name__ == '__main__':
    main()