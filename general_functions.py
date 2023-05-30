import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Filters, MessageHandler, Updater, CommandHandler, CallbackQueryHandler, ConversationHandler
from json_token import save_data
from config import TRELLO_KEY, TELEGRAM_TOKEN
from for_boards import *
from for_cards import *

bot = telegram.Bot(TELEGRAM_TOKEN)

def start(update, context):
    message = 'нажмите на кнопку для регистрации в Trello, необходимо одним сообщением выслать свой токен (только сам токен):'
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text='войти в Trello', url='https://trello.com/1/connect?key=' + TRELLO_KEY + '&name=TelegramBot&response_type=token&scope=read,write')]]
    )
    context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_markup=reply_markup)
    return 'token'


def check_token(token):
    url = f'https://api.trello.com/1/members/me?key={TRELLO_KEY}&token={token}'
    response = requests.get(url)
    return response.ok


def trello(update, context):
    token = update.message.text.strip()
    chat_id = update.effective_chat.id
    if check_token(token):
        save_data(token, chat_id)
        menu(update, context)
        return ConversationHandler.END
    else:
        error_message = 'некорректный токен. пожалуйста, введите корректный токен API Trello'
        context.bot.send_message(chat_id=chat_id, text=error_message)
        return
  

def menu(update, context):
    chat_id = update.effective_chat.id

    sign_out_button = InlineKeyboardButton(text='сменить аккаунт', callback_data='sign_out')
    show_boards_button = InlineKeyboardButton('к списку досок', callback_data='back_to_board_list')
    show_inf_board_button = InlineKeyboardButton(text='информация о доске', callback_data='get_board_info')
    summary_info_button = InlineKeyboardButton(text='о EnergoinzTrelloBot', callback_data='summary_info')
    
    keyboard = [[sign_out_button], [show_inf_board_button], [show_boards_button], [summary_info_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(chat_id=chat_id, text='выберите действие', reply_markup=reply_markup)


# вывод краткой информации о боте
def bot_summary_info(update, context):
    chat_id = update.effective_chat.id

    message = 'EnergoinzTrelloBot может:\n'
    message += '* вывести информацию о конкретной карточке или доске\n'
    message += '* создать доску или карточку в Trello\n'
    message += '* импортировать созданную вне бота доску для получения уведомлений\n'
    message += '* присылать уведомления:\n'
    message += '** о создании новой карточки другим пользователем\n'
    message += '** о назначении Вас ответственным карточки другим пользователем\n'
    message += '** о переносе карточки в другой список другим пользователем\n'
    message += '** о других изменениях в Trello, сделанных другим пользователем\n'

    to_menu_button = InlineKeyboardButton(text='назад', callback_data='menu')
    reply_markup = InlineKeyboardMarkup([[to_menu_button]])
    
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)


def send_message(chat_id, message):
    bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')


def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      CallbackQueryHandler(start, pass_user_data=True, pattern='sign_out')],
        states={
            'token': [MessageHandler(Filters.text & ~Filters.command, trello)]
        },
        fallbacks=[],
        per_user=True,
    )

    dp.add_handler(start_conv_handler)

    # вывод краткой информации о боте
    dp.add_handler(CallbackQueryHandler(bot_summary_info, pass_user_data=True, pattern='summary_info'))
    # возврат к меню
    dp.add_handler(CallbackQueryHandler(menu, pass_user_data=True, pattern='menu'))

    dp.add_handler(CallbackQueryHandler(show_boards, pass_user_data=True, pattern='back_to_board_list'))

    dp.add_handler(create_board_handler())
    dp.add_handler(board_info_handler())

    dp.add_handler(board_members_handler())

    # добавим ConversationHandler для завершения создания карточки
    dp.add_handler(finish_cr_conv_handler())

    dp.add_handler(CallbackQueryHandler(card_list, pass_user_data=True, pattern='^board_id(.*)$'))

    # добавляем webhook для доски 
    dp.add_handler(CallbackQueryHandler(update_webhook, pass_user_data=True, pattern='^set_webhook(.*)$'))

    # добавим ConversationHandler для вывода информации о карточке
    dp.add_handler(card_info_conv_handler())
    dp.add_handler(CallbackQueryHandler(show_card_options, pass_user_data=True, pattern='edit_card'))

    # для редактирования карточки
    # перемещение по столбцам
    dp.add_handler(CallbackQueryHandler(choose_column_handler, pass_user_data=True, pattern='choose_column_handler'))
    dp.add_handler(CallbackQueryHandler(move_card_to_column, pass_user_data=True, pattern='^change_column(.*)$'))

    # измение названия
    dp.add_handler(new_card_name_handler())

    # добавим ConversationHandler для архивации карточки
    dp.add_handler(archive_card_handler())

    updater.start_polling()

    updater.idle()
