import re
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ConversationHandler, Filters, MessageHandler
from json_token import load_token
from config import TRELLO_KEY, CALLBACK_URL


def get_trello_member_username(member_id, TRELLO_KEY, token):
    url = f'https://api.trello.com/1/members/{member_id}'
    params = {
        'key': TRELLO_KEY,
        'token': token
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        member = response.json()
        return member['username']
    else:
        raise Exception(f'Error {response.status_code} - {response.text}')


def get_context_data(update):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    return chat_id, message_id, query


# список досок пользователя в виде кнопок
def generate_board_buttons(context, boards_data, token):
    buttons = []
    for board in boards_data:
        board_id = board['id']
        context.user_data[board_id] = {'id': board_id, 'token': token}
        button = InlineKeyboardButton(text=board['name'], callback_data=f'board_id{board_id}')
        buttons.append([button])

    return buttons

# проверка: есть ли у пользователя доски
def has_boards(token):
    boards_url = f'https://api.trello.com/1/members/me/boards?key={TRELLO_KEY}&token={token}'
    response = requests.get(boards_url)
    boards_data = response.json()

    if response.status_code != 200:
        return False

    return bool(boards_data)

# у пользователя нет досок
def emty_boards_data(context, chat_id):
    # если у пользователя нет досок
    message = 'у Вас нет ни одной доски в Trello...'
    # добавляем кнопку для создания новой доски
    create_board_button = InlineKeyboardButton(text='создать доску', callback_data='new_board')
    reply_markup = InlineKeyboardMarkup([[create_board_button]])
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)
    return

# вывод списка досок в виде кнопок + кнопок создания доски и краткой информации
def show_boards(update, context):
    chat_id = update.effective_chat.id
    token = load_token(chat_id)

    if not token:
        context.bot.send_message(chat_id=chat_id, text='сначала необходимо зарегистрироваться.')
        return

    boards_url = f'https://api.trello.com/1/members/me/boards?key={TRELLO_KEY}&token={token}'
    response = requests.get(boards_url)
    boards_data = response.json()

    if response.status_code != 200:
        message = 'Ошибка: ' + response.text
        context.bot.send_message(chat_id=chat_id, text=message)
        return
    # список досок пользователя пуст
    if not boards_data:
        emty_boards_data(context, chat_id)
    
    message = 'Ваши доски в Trello:\n'
    buttons = generate_board_buttons(context, boards_data, token)

    # добавляем кнопку для создания новой доски
    new_board_button = InlineKeyboardButton(text='создать доску', callback_data='new_board')
    show_inf_board_button = InlineKeyboardButton(text='информация о доске', callback_data='get_board_info')
    menu_button = InlineKeyboardButton(text='меню', callback_data='menu')
    buttons.append([new_board_button, show_inf_board_button, menu_button])

    reply_markup = InlineKeyboardMarkup(buttons)
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)


def create_board_callback(update, context):
    chat_id = update.callback_query.message.chat_id

    # Запрашиваем у пользователя название новой доски
    update.callback_query.answer()
    text = 'введите название для новой доски:'

    # Добавляем кнопку 'Отмена'
    cancel_button = InlineKeyboardButton(text='отмена', callback_data='cancel_board_creation')
    reply_markup = InlineKeyboardMarkup([[cancel_button]])
    context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    # Ожидаем ответа пользователя с названием новой доски
    return 'ask_board_name'


def cancel_board_creation(update):
    query = update.callback_query
    query.answer()
    query.edit_message_text(text='создание доски отменено')
    return ConversationHandler.END


def visibility_keyboard():
    keyboard = [
        [InlineKeyboardButton('Public', callback_data='public')],
        [InlineKeyboardButton('Private', callback_data='private')]
    ]
    return InlineKeyboardMarkup(keyboard)


def save_board_name(update, context):
    chat_id = update.message.chat_id
    message_id = update.message.message_id

    board_name = update.message.text
    if board_name.lower() == 'отмена':
        # удаляем предыдущее сообщение от бота
        context.bot.delete_message(chat_id=chat_id, message_id=message_id-1)

        context.bot.send_message(chat_id=update.effective_chat.id, text='создание доски отменено')
        return ConversationHandler.END
    context.user_data['new_board_name'] = board_name

    # удаляем предыдущее сообщение от бота
    context.bot.delete_message(chat_id=chat_id, message_id=message_id-1)
    # запрашиваем у пользователя видимость новой доски
    update.message.reply_text('укажите видимость новой доски:', reply_markup=visibility_keyboard())

    # ожидаем ответа пользователя с видимостью новой доски
    return 'ask_board_visibility'


# добавляем webhook к доске
def set_webhook(token, board_id):
    webhook_url = f'https://api.trello.com/1/tokens/{token}/webhooks/?key={TRELLO_KEY}'
    callback_url = CALLBACK_URL + '/webhook' 
    webhook_params = {
        'description': 'Webhook for board updates',
        'callbackURL': callback_url,
        'idModel': board_id,
    }
    requests.post(webhook_url, data=webhook_params)

    if requests.post(webhook_url, data=webhook_params).text == 'A webhook with that callback, model, and token already exists':
        return 'WEBHOOK_SET'
    else:
        return 'ERROR'


def update_webhook(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    token = load_token(chat_id)
    
    # изначальное значение текста сообщения
    message = 'что-то полшло не так... попробуйте снова'
    if 'set_webhook' in query.data :
        # получаем board_id из pattern
        match = re.match(r'^set_webhook(.*)$', query.data)
        board_id = match.group(1)
        if set_webhook(token, board_id) == 'WEBHOOK_SET':
            message = 'webhook установлен!'
            
    context.bot.send_message(chat_id=chat_id, text=message)


def save_board_visibility(update, context):
    visibility = update.callback_query.data
    board_name = context.user_data.get('new_board_name')
    token = load_token(update.effective_chat.id)
    query_message = update.callback_query.message
    chat_id = query_message.chat_id
    message_id = query_message.message_id

    if not token:
        message = 'Ошибка: не удалось загрузить токен'
    else:
        board_url = f'https://api.trello.com/1/boards?key={TRELLO_KEY}&token={token}&name={board_name}&prefs_permissionLevel={visibility}'
        response = requests.post(board_url)

        if response.status_code == 200 and response.content:
            board_data = response.json()

            set_webhook(token, board_data['id'])

            context.user_data[str(len(context.user_data))] = {'id': board_data['id'], 'token': token}
            # удаляем предыдущее сообщение от бота
            context.bot.delete_message(chat_id=chat_id, message_id=message_id)

            message = f'доска {board_name} успешно создана!'
            context.bot.send_message(chat_id=update.effective_chat.id, text=message)

            board_link = f"{board_data['url']}"
            
            context.bot.send_message(chat_id=update.effective_chat.id, text=f'ссылка на доску: {board_link}')
        else:
            # удаляем предыдущее сообщение от бота
            context.bot.delete_message(chat_id=chat_id, message_id=message_id)

            message = 'Ошибка: не удалось создать доску'
            context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    show_boards(update, context)
    return ConversationHandler.END


def get_trello_board(board_id, api_key, api_token):
    url = f'https://api.trello.com/1/boards/{board_id}'
    params = {
        'key': api_key,
        'token': api_token,
        'cards': 'all',  # получить информацию обо всех карточках доски
        'lists': 'all',  # получить информацию обо всех списках доски
        'memberships': 'none',  # не получать информацию о участниках доски
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_board_members(board_id, token):
    members_url = f'https://api.trello.com/1/boards/{board_id}/members?key={TRELLO_KEY}&token={token}'
    members_response = requests.get(members_url)
    if members_response.status_code == 200 and members_response.content:
        members_data = members_response.json()
        members = [member['username'] for member in members_data]
        members_message = '<b>участники доски:</b>\n' + '\n'.join(members)
    else:
        members_message = 'Ошибка: не удалось получить список участников доски'
    return members_message


def start_board_info(update, context):
    query_message = update.callback_query.message
    chat_id = query_message.chat_id
    message_id = query_message.message_id

    token = load_token(chat_id)

    # удаляем предыдущее сообщение от бота
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    boards_url = f'https://api.trello.com/1/members/me/boards?key={TRELLO_KEY}&token={token}'
    response = requests.get(boards_url)
    boards_data = response.json()

    # список досок пользователя пуст
    if not boards_data: 
        emty_boards_data(context, chat_id)
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(generate_board_buttons(context, boards_data, token))
    context.bot.send_message(chat_id=chat_id, text='выберите доску:', reply_markup=reply_markup)

    return 'board_selected'


def get_board_info_handler(update, context):
    chat_id, message_id, query = get_context_data(update)

    # получаем board_id из callback_data
    board_id = query.data.replace('board_id', '')
    selected_board = None

    # запрос к API Trello для получения информации о доске
    token = load_token(chat_id)
    board_url = f'https://api.trello.com/1/boards/{board_id}?key={TRELLO_KEY}&token={token}'
    response = requests.get(board_url)

    if response.status_code == 200:
        board_data = response.json()
        selected_board = board_data.get('name')

    if not selected_board:
        context.bot.send_message(chat_id=chat_id, text='Ошибка: доска не найдена')
        return ConversationHandler.END

    context.user_data['selected_board'] = selected_board

    # удаляем предыдущее сообщение от бота
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    context.bot.send_message(chat_id=chat_id, text=f'выбрана доска: {selected_board}. вывожу информацию о ней...')
    show_board_info(update, context)


def check_webhook_exists(board_id, token):
    url = f"https://api.trello.com/1/tokens/{token}/webhooks"
    params = {
        'key': TRELLO_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        webhooks = response.json()
        for webhook in webhooks:
            if webhook['idModel'] == board_id:
                return True
        return False
    else:
        return False


def show_board_info(update, context):
    chat_id = update.callback_query.message.chat_id
    board_name = context.user_data['selected_board']
    token = load_token(chat_id)

    board_id = get_board_id_by_name(board_name, token)
    if not board_id:
        context.bot.send_message(chat_id=chat_id, text=f'доска {board_name} не найдена')
        return ConversationHandler.END

    board = get_trello_board(board_id, TRELLO_KEY, token)
    board_name = board['name']
    members = get_board_members(board_id, token)
    creator_name = members.split('\n')[1].strip()
    board_url = board['shortUrl']

    message = f'<b>название доски:</b> {board_name}\n<b>создатель:</b> {creator_name}\n{members}\n<b>ссылка на доску:</b> {board_url}'
    context.bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')

    keyboard = [[InlineKeyboardButton('к списку карточек', callback_data=f'board_id{board_id}'),
                 InlineKeyboardButton('к списку досок', callback_data='back_to_board_list')]]

    keyboard.append([InlineKeyboardButton('импортировать', callback_data=f'set_webhook{board_id}')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(chat_id=chat_id, text='выберите действие:', reply_markup=reply_markup)

    # удаляем сохраненное значение selected_board из контекста
    context.user_data.pop('selected_board', None)

    return ConversationHandler.END



def get_board_id_by_name(board_name, token):
    url = f'https://api.trello.com/1/members/me/boards?key={TRELLO_KEY}&token={token}'
    response = requests.get(url)
    boards = response.json()
    for board in boards:
        if board['name'].lower() == board_name.lower():
            return board['id']
    return None


def create_board_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(create_board_callback, pattern='new_board')],
        states={
            'ask_board_name': [MessageHandler(Filters.text, save_board_name)],
            'ask_board_visibility': [CallbackQueryHandler(save_board_visibility, pattern='^(public|private)$')],
        },
        fallbacks=[CallbackQueryHandler(cancel_board_creation, pattern='cancel_board_creation')],
        allow_reentry=True
    )


def board_info_handler():
    return  ConversationHandler(
        entry_points=[CallbackQueryHandler(start_board_info, pattern='get_board_info')],
        states={
            'board_selected': [CallbackQueryHandler(get_board_info_handler, pattern='^board_id(.*)$')],
        },
        fallbacks=[],
    )
