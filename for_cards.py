from datetime import datetime
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
import requests
from telegram.error import TelegramError
from json_token import load_token
from config import TRELLO_KEY
from for_boards import *


def add_back_buttons(board_id):
    keyboard = [[InlineKeyboardButton('К списку карточек', callback_data=f'board_id{board_id}'),
                 InlineKeyboardButton('К списку досок', callback_data='back_to_board_list')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def unknown(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text='что-то пошло не так..... пожалуйста, попробуйте еще раз')


# вывод кнопок после сообщения нажатия на кнопку Редактировать карточку
def show_card_options(update, context):
    chat_id, message_id, query = get_context_data(update)
    board_id = context.user_data.get('board_id')

    # Удаляем предыдущее сообщение от бота
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    keyboard = [
        [InlineKeyboardButton('перенести в другой список', callback_data='choose_column_handler')],
        [InlineKeyboardButton('переименовать', callback_data='rename_card')],
        [InlineKeyboardButton('редактировать состав участников', callback_data='update_card_members')],
        [InlineKeyboardButton('архивировать карточку', callback_data='archive_card')],
        [InlineKeyboardButton('к списку карточек', callback_data=f'board_id{board_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.message.reply_text('выберите действие:', reply_markup=reply_markup)


def get_trello_cards(board_id, TRELLO_KEY, token):
    url = f'https://api.trello.com/1/boards/{board_id}/cards'
    params = {
        'key': TRELLO_KEY,
        'token': token
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f'Error {response.status_code} - {response.text}')


def get_board_cards(board_data, TRELLO_KEY, token):
    board_url = f"https://api.trello.com/1/boards/{board_data['id']}/lists?key={TRELLO_KEY}&token={token}"

    response = requests.get(board_url)
    if response.status_code == 200 and response.content:
        lists_data = response.json()
        message = ''
        for lst in lists_data:
            message += f"{lst['name']}:\n"
            list_url = f"https://api.trello.com/1/lists/{lst['id']}/cards?key={TRELLO_KEY}&token={token}"
            response = requests.get(list_url)
            if response.status_code == 200 and response.content:
                cards_data = response.json()
                cards = [f"{i+1}. {card['name']}" for i, card in enumerate(cards_data)]
                message += '\n'.join(cards) + '\n\n'
            else:
                message += 'Ошибка: не удалось получить данные о карточках\n\n'
    else:
        message = 'Ошибка: не удалось получить данные о столбцах'

    return message


def card_list(update, context, board_id=None):
    query = update.callback_query
    chat_id = query.message.chat_id
    token = load_token(chat_id)

    if token is not None:
        if board_id is None:
            board_id = re.match('^board_id(.*)$', query.data).group(1)

        board_data = context.user_data.get(board_id, {})
        if not board_data.get('id'):
            context.bot.send_message(chat_id=chat_id, text='вы ещё не создавали досок')
            return
        
        if not board_data.get('columns'):
            board_url = f"https://api.trello.com/1/boards/{board_data['id']}?lists=open&list_fields=name&key={TRELLO_KEY}&token={token}"
            response = requests.get(board_url)
            if response.status_code != 200:
                message = 'Ошибка: ' + response.text
                context.bot.send_message(chat_id=chat_id, text=message)
                return
            
            board_data['columns'] = [{'id': column['id'], 'name': column['name']} for column in response.json()['lists']]
            context.user_data['board_id'] = board_id

        members_message = get_board_members(board_data['id'], token)

        message = get_board_cards(board_data, TRELLO_KEY, token)
        
        button_card_information = InlineKeyboardButton('информация о конкретной карточке', callback_data='card_information')
        button_add = InlineKeyboardButton('добавить карточку', callback_data='choose_board_members')
        button_del = InlineKeyboardButton('архивировать карточку', callback_data='archive_card')
        button_back_to_board = InlineKeyboardButton('назад к списку досок', callback_data='back_to_board_list')

        keyboard = [[button_card_information], [button_add, button_del], [button_back_to_board]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_message(chat_id=chat_id, text=members_message, parse_mode='HTML')
        context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)

    else:
        message = 'Ошибка: не удалось загрузить токен'
        context.bot.send_message(chat_id=chat_id, text=message)


def get_member_id(username, trello_key, token):
    url = f'https://api.trello.com/1/members/{username}?key={trello_key}&token={token}'
    response = requests.get(url)
    if response.status_code == 200 and response.content:
        member_data = response.json()
        return member_data['id']
    return None


def choose_board_members_handler(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id

    # получить board_id и user_data
    board_id = context.user_data.get('board_id')
    token = load_token(chat_id)
    members_url = f'https://api.trello.com/1/boards/{board_id}/members?key={TRELLO_KEY}&token={token}'
    members_response = requests.get(members_url)
    if members_response.status_code == 200 and members_response.content:
        members_data = members_response.json()
        members = [member['username'] for member in members_data]
        members_keyboard = []

        for member in members:
            member_id = get_member_id(member, TRELLO_KEY, token)
            members_keyboard.append([InlineKeyboardButton(member, callback_data=f'{member_id}')])

        # done_members для создания карточки, update_members для редактирования
        callback_data = 'update_members' if query.data == 'update_card_members' else 'done_members'
        members_keyboard.append([InlineKeyboardButton('все участники выбраны', callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(members_keyboard)
        context.bot.send_message(chat_id=chat_id, text='выберите участников доски для этой карточки:', reply_markup=reply_markup)

        return 'CHOOSING_MEMBERS' 
    
    return 'ERROR'


def choosing_members_handler(update, context):
    query = update.callback_query

    if query.data == 'done_members':
        try:
            choose_column_handler(update, context)

            return ConversationHandler.END
                
        except TelegramError as e:
            # print(f'Error deleting message: {e}')
            return 'ERROR'
        
    # процесс изменения учатсников доски
    elif query.data == 'update_members':
        query = update.callback_query
        chat_id = query.message.chat_id
        token = load_token(chat_id)
        card_id = context.user_data.get('card_id')

        if context.user_data['selected_members'] is not None:
            message = update_card_members(card_id, TRELLO_KEY, token, context.user_data['selected_members'])
            context.bot.send_message(chat_id=chat_id, text=message)

            context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(context.user_data.get('board_id')))
            return ConversationHandler.END
        else:
            return 'CHOOSING_MEMBERS'
    else:
        # храним только уникальные id участников карточки
        selected_members = context.user_data.get('selected_members', [])
        selected_members.append(query.data) if query.data not in selected_members else None
        context.user_data['selected_members'] = selected_members
        context.bot.answer_callback_query(callback_query_id=query.id)

        return 'CHOOSING_MEMBERS'


def update_card_members(card_id, trello_key, token, member_ids=None):
    url = f'https://api.trello.com/1/cards/{card_id}?key={trello_key}&token={token}'
    payload = {'idMembers': ','.join(member_ids)}
    response = requests.put(url, data=payload)
    if response.status_code == 200:
        return 'Участники карточки успешно обновлены'
    else:
        return 'Произошла ошибка при обновлении участников карточки'


def choose_column_handler(update, context):
    user_data = context.user_data

    chat_id, message_id, query = get_context_data(update)

    # удаляем предыдущее сообщение от бота
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    # получить board_id и selected_members
    board_id = user_data.get('board_id')
    selected_members = user_data.get('selected_members', [])

    # получение списков доски
    columns_url = f'https://api.trello.com/1/boards/{board_id}/lists?key={TRELLO_KEY}&token={load_token(chat_id)}'
    columns_response = requests.get(columns_url)

    if columns_response.status_code == 200 and columns_response.content:
        columns_data = columns_response.json()
        columns = []
        for column in columns_data:
            if query.data == 'choose_column_handler':
                columns.append([InlineKeyboardButton(column['name'], callback_data=f"change_column{column['id']}")])
            else:
                columns.append([InlineKeyboardButton(column['name'], callback_data=f"column_{column['id']}")])
        columns.append([InlineKeyboardButton('отмена', callback_data='cancel')])

        reply_markup = InlineKeyboardMarkup(columns)
        context.bot.send_message(chat_id=chat_id, text='выберите список для этой карточки:', reply_markup=reply_markup)

        # изменить column_id и selected_members в user_data для create_card_handler
        user_data.update({'selected_members': selected_members, 'column_id': None})
        return 'CHOOSING_COLUMN'

    return 'ERROR'



def create_card_handler(update, context):
    chat_id, message_id, query = get_context_data(update)
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    create_card_data = context.user_data
    board_id = create_card_data.get('board_id')
    column_id = re.match('^column_(.*)$', query.data).group(1)
    
    context.user_data['board_id'] = board_id
    context.user_data['column_id'] = column_id

    # определяем занчение (последовательность из ноля)
    CARD_NAME = range(1)

    context.bot.send_message(chat_id=chat_id, text='введите название для новой карточки:')
    return CARD_NAME


def create_card_message_handler(update, context):
    chat_id = update.message.chat_id
    token = load_token(chat_id)
    create_card_data = context.user_data
    column_id = create_card_data.get('column_id')
    members = create_card_data.get('selected_members')

    card_name = update.message.text

    message = create_card(column_id, card_name, TRELLO_KEY, token, members)
    context.bot.send_message(chat_id=chat_id, text=message)

    # очищаем user_data
    context.user_data.pop('create_card', None)
    context.user_data.pop('selected_members', None)


    current_board_id = context.user_data.get('board_id')
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(current_board_id))
    return ConversationHandler.END


def create_card(column_id, card_name, trello_key, token, members=None):
    url = f'https://api.trello.com/1/cards?key={trello_key}&token={token}&name={card_name}&idList={column_id}'
    if members:
        for member in members:
            url += f'&idMembers={member}'
    response = requests.post(url)
    if response.status_code == 200:
        return 'карточка успешно создана'
    else:
        return 'произошла ошибка при создании карточки'


def start_archive_card_handler(update, context):
    context.user_data['archive_card'] = True
    message = 'введите название карточки для архивации:'
    keyboard = [[InlineKeyboardButton('отмена', callback_data='cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=update.callback_query.message.chat_id,
                             text=message,
                             reply_markup=reply_markup)

    return 'ARCHIVE_CARD'


def confirm_archive_card_handler(update, context):
    chat_id = update.message.chat_id
    token = load_token(chat_id)
    card_name = update.message.text

    current_board_id = context.user_data.get('board_id')
    cards_data = get_trello_cards(current_board_id, TRELLO_KEY, token)

    card_id = None
    for card in cards_data:
        if card['name'] == card_name:
            card_id = card['id']
            archive_card(card_id, TRELLO_KEY, token)
            break

    if card_id is not None:
        cards_data = get_trello_cards(current_board_id, TRELLO_KEY, token)
        board_data = context.user_data.get(current_board_id, {})
        message = get_board_cards(board_data, TRELLO_KEY, token)
        context.user_data['board_id'] = current_board_id
        update.message.reply_text(f'карточка {card_name} архивирована\n\n{message}')
    else:
        update.message.reply_text(f'карточка {card_name} не найдена на доске')

    context.user_data.pop('archive_card', None)


    current_board_id = context.user_data.get('board_id')
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(current_board_id))
    return ConversationHandler.END


def cancel_archive_card_handler(update, context):
    chat_id = update.message.chat_id
    context.bot.send_message(chat_id=update.callback_query.message.chat_id,
                             text='архивация карточки отменена')
    context.user_data.pop('archive_card', None)

    current_board_id = context.user_data.get('board_id')
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(current_board_id))
    return ConversationHandler.END


def archive_card(card_id, trello_key, token):
    url = f'https://api.trello.com/1/cards/{card_id}?key={trello_key}&token={token}&closed=true'
    response = requests.put(url)
    if response.status_code == 200:
        return 'Карточка успешно архивирована'
    else:
        return 'Произошла ошибка при архивировании карточки'
    

def start_show_card_info(update, context):
    chat_id = update.callback_query.message.chat_id
    context.user_data['command'] = 'show_card_info'

    keyboard = [[InlineKeyboardButton('отмена', callback_data='cancel_show')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text='введите название карточки для вывода информации о ней:', reply_markup=reply_markup)
    
    return 'GET_CARD_NAME'


def get_card_name(update, context):
    chat_id = update.message.chat_id
    card_name = update.message.text
    board_id = context.user_data.get('board_id')
    token = load_token(chat_id)

    cards = get_trello_cards(board_id, TRELLO_KEY, token)
    card = next((card for card in cards if card['name'] == card_name), None)

    if card is None:
        context.bot.send_message(chat_id=chat_id, text=f'карточка {card_name} не найдена')
        return ConversationHandler.END

    context.user_data['card_name'] = card_name
    show_card_info(update, context)

    keyboard = [[InlineKeyboardButton('к списку карточек', callback_data=f'board_id{board_id}'),
                 InlineKeyboardButton('редактировать', callback_data='edit_card')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=reply_markup, parse_mode='HTML')
    return ConversationHandler.END


def show_card_info(update, context):
    chat_id = update.message.chat_id
    card_name = context.user_data['card_name']

    board_id = context.user_data.get('board_id')
    token = load_token(chat_id)

    cards = get_trello_cards(board_id, TRELLO_KEY, token)
    card = next((card for card in cards if card['name'] == card_name), None)
    card_id = card['id']
    context.user_data['card_id'] = card_id

    # получаем информацию о доске по ее ID
    board = get_trello_board(board_id, TRELLO_KEY, token)

    # формируем текст сообщения с информацией о карточке и доске
    message = f"<b>название карточки: {card['name']}</b>\n" \
              f"<b>название доски: {board['name']}</b>\n"
              
    # форматируем дату создания карточки в нужный формат
    date_of_last_activity = datetime.strptime(card['dateLastActivity'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%d %B %Y, %H:%M')
    message += f'<b>дата последней активности:</b> {date_of_last_activity}\n'

    message += '<b>участники:</b>\n'
    
    # если у карточки нет участников, добавляем сообщение об этом
    if not card['idMembers']:
        message += '- участников нет\n\n'
    else:
        for member in card['idMembers']:
            member_name = get_trello_member_username(member, TRELLO_KEY, token)
            message += f'- {member_name}\n'

    # добавляем список вложений карточки, если он есть
    attachments = card.get('attachments', [])
    if attachments:
        message += '<b>вложения:</b>\n\n'
        for attachment in attachments:
            message += f"- {attachment['name']} ({attachment['url']})\n"

    # добавляем ссылку на карточку
    card_url = f"https://trello.com/c/{card['shortLink']}"
    message += f"<a href='{card_url}'>ссылка на карточку</a>"

    # отправляем сообщение с информацией о карточке и кнопками 'к списку карточек' и 'к списку досок'
    add_back_buttons(chat_id)
    context.bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')
    context.user_data.pop('card_name', None)  # Удаляем сохраненное название карточки из контекста


def move_card_to_column(update, context):
    chat_id, message_id, query = get_context_data(update)
    token = load_token(chat_id)

    # полчуение card_id и column_id из callback_data
    card_id = context.user_data.get('card_id')
    match = re.match(r'^change_column(.*)$', query.data)
    column_id = match.group(1)

    try:
        # перенос карточки в выбранный список
        url = f'https://api.trello.com/1/cards/{card_id}/idList'
        params = {'value': column_id, 'key': TRELLO_KEY, 'token': token}
        response = requests.put(url, params=params)

        context.bot.answer_callback_query(callback_query_id=query.id, text='карточка успешно перенесена!')
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    except:
        context.bot.answer_callback_query(callback_query_id=query.id, text='не удалось перенести карточку, попробуйте еще раз')

    
    current_board_id = context.user_data.get('board_id')
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(current_board_id))

    # удаляем сохраненное значение card_id из контекста
    context.user_data.pop('card_id', None)
    return ConversationHandler.END


def update_trello_card_name(card_id, new_name, key, token):
    url = f'https://api.trello.com/1/cards/{card_id}'
    query = {'name': new_name, 'key': key, 'token': token}

    response = requests.put(url, params=query)
    if response.status_code == requests.codes.ok:
        return True

    return False


def change_card_name(update, context):
    chat_id = update.message.chat_id
    context.user_data['card_name'] = update.message.text
    card_name = context.user_data['card_name']
    card_id = context.user_data.get('card_id')

    # получаем ID доски и токен доступа пользователя
    token = load_token(chat_id)

    # обновляем название карточки на Trello
    success = update_trello_card_name(card_id, card_name, TRELLO_KEY, token)

    # проверяем успешность обновления названия карточки
    if success:
        # отправляем сообщение об успешном обновлении названия карточки
        message = f'название карточки успешно изменено на {card_name}'
    else:
        # отправляем сообщение об ошибке при обновлении названия карточки
        message = 'Ошибка при обновлении названия карточки, попробуйте еще раз.'

    context.bot.send_message(chat_id=chat_id, text=message)

    # очищаем сохраненные данные о карточке из контекста
    context.user_data.pop('card_id', None)
    context.user_data.pop('card_name', None)

    current_board_id = context.user_data.get('board_id')
    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=add_back_buttons(current_board_id))
    return ConversationHandler.END


def request_new_card_name(update, context):
    query = update.callback_query
    # сохраняем ID карточки, для которой нужно изменить название
    card_id = context.user_data.get('card_id')

    # запрашиваем у пользователя новое название карточки
    message = 'введите новое название карточки:'
    context.bot.send_message(chat_id= query.message.chat_id, text=message)

    # сохраняем ID карточки в контексте
    context.user_data['card_id'] = card_id

    return 'WAIT_FOR_NAME'


# добавим ConversationHandler для удаления карточки
def archive_card_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_archive_card_handler, pattern='archive_card')],
        states={
            'ARCHIVE_CARD': [MessageHandler(Filters.text, confirm_archive_card_handler)]
        },
        fallbacks=[CallbackQueryHandler(cancel_archive_card_handler, pattern='cancel_show')]
    )


# добавим ConversationHandler для вывода информации о карточке
def card_info_conv_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_show_card_info, pass_user_data=True, pattern='card_information')
        ],
        states={
            'GET_CARD_NAME': [MessageHandler(Filters.text, get_card_name)],
        },
        fallbacks=[CallbackQueryHandler(card_list, pattern='cancel')],  # если нажать на отмену будет выведен список карточек
        allow_reentry=True
    )


# и для редактирования, и для создания карточки, в зависимости от callback_data
def board_members_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_board_members_handler, pattern='choose_board_members'),
                      CallbackQueryHandler(choose_board_members_handler, pattern='update_card_members')],
        states={
            'CHOOSING_MEMBERS': [CallbackQueryHandler(choosing_members_handler)],
            'ERROR' : [CallbackQueryHandler(unknown)]
        },
        fallbacks=[],
        per_user=True,
    )

# добавим ConversationHandler для завершения создания карточки
def finish_cr_conv_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(create_card_handler, pass_user_data=True, pattern='^column_(.*)$')
        ],
        states={
            range(1): [MessageHandler(Filters.text, create_card_message_handler)]
        },
        fallbacks=[],
        allow_reentry=True
    )


def new_card_name_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(request_new_card_name, pass_user_data=True, pattern='rename_card')],
        states={
            'WAIT_FOR_NAME': [MessageHandler(Filters.text, change_card_name)]
        },
        fallbacks=[],
        per_user=True,
    )