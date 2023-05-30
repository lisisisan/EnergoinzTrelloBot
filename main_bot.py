# -*- coding: utf-8 -*-
import json
from threading import Thread
from flask import Flask, request
import requests
from general_functions import send_message
from config import TRELLO_KEY

from general_functions import main

# создаем экземпляр класса Flask
app = Flask(__name__)

# хранение идентификаторов уже обработанных событий
processed_events = set()  

# определяем маршрут для корневой страницы
@app.route('/')
def hello_world():
    return 'Hello, World!'


# получаем id плоьзователя по его токену
def get_user_id(token):
    url = f"https://api.trello.com/1/tokens/{token}/member"
    params = {
        'key': TRELLO_KEY,  
        'token': token
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        user_data = response.json()
        user_id = user_data['id']
        return user_id
    else:
        # ошибка при получении идентификатора пользователя
        return None


# получем название карточки и username пользователя, который сделал это действие
def get_card_and_member_names(json_data):
    card_name = json_data['action']['data']['card']['name']
    member_creator_username = json_data['action']['memberCreator']['username']

    return card_name, member_creator_username


# добавляем ссылку на карточку
def add_card_url(action_data):
    card_url = f"https://trello.com/c/{action_data['card']['shortLink']}"
    card_url_message = f"<a href='{card_url}'>ссылка на карточку</a>"

    return card_url_message


# формируем сообщение при создании карточки
def create_card_message(action_data, card_name, member_creator_username):
    message = f"<b>создана новая карточка:</b> {card_name}\n"

    # добавляем название колонки
    list_name = action_data['list']['name']
    message += f"<b>в колонке</b> {list_name}\n"

    # добавляем ник создателя
    message += f"<b>создал пользователь</b> {member_creator_username}\n\n"

    return message


@app.route('/webhook', methods=['POST', 'HEAD'])
def trello_webhook():

    if request.method == 'HEAD':
        return 'OK'
    
    else:
        json_data = request.json

        # проверяем, что событие ещё не было обработано
        event_id = json_data.get('id')
        if event_id in processed_events:
            return 'Success'

        with open('data.json', 'r') as file:
            data = json.load(file)
        
        # проходимся по всем, кто зарегистрирован в боте
        for token, chat_id in data.items():
            boards_url = f"https://api.trello.com/1/members/me/boards?key={TRELLO_KEY}&token={token}"
            response = requests.get(boards_url)
            
            if response.status_code == 200:
                board_ids = [board['id'] for board in response.json()]
                memberCreator_id = json_data['action']['memberCreator']['id']
                
                # если пользователь с токеном == token находится в доске, где произошли изменения, НО мы не присылаем уведомления тому, кто совершил действие
                # if json_data['model']['id'] in board_ids and get_user_id(token) != memberCreator_id:
                if json_data['model']['id'] in board_ids:
                    action_type = json_data['action']['type']

                    action_data = json_data['action']['data']
                    card_name, member_creator_username = get_card_and_member_names(json_data)

                    # карточка была создана 
                    if action_type == 'createCard':
                        # функция для создания сообщения при action type createCard
                        message = create_card_message(action_data, card_name, member_creator_username)

                    elif action_type == 'updateCard':

                        # карточка была перемещена в другой список
                        if 'listAfter' in action_data:

                            list_before = action_data.get('listBefore', {}).get('name')
                            list_after = action_data['listAfter']['name']
                            message = f"<b>карточка</b> {card_name} <b>была перемещена из списка</b> {list_before} <b>в список</b> {list_after}\n"

                        # карточка была архивирована
                        elif action_data['card']['closed']:

                            message = f"<b>карточка</b> {card_name} <b>была архивирована</b>\n"

                        # добавляем usernamу пользователя, который совершил действие
                        message += f"<b>пользователем</b> {member_creator_username}\n\n"
                    elif action_type == 'addMemberToCard':

                        # если пользователь был добавлен к карточке, то только ему придет уведомление
                        message = f"<b>Вы были добавлены к карточке</b> {card_name}\n"

                    else:
                        # message = f'<b>произошли изменения в карточке</b> {card_name}\n\n'
                        return

                    # добавляем ссылку на карточку
                    message += add_card_url(action_data)            

                    # отправляем сообщение нужному пользователю
                    send_message(chat_id, message)
                    # добавляем идентификатор в обработанные события
                    processed_events.add(event_id)  

            else:
                # print(f'Ошибка при получении списка досок для чата {chat_id}, код {response.status_code}')
                return 'ERROR'

    return 'Success'


def run():
    app.run(host='0.0.0.0', port=5000)


if __name__ == '__main__':
    t = Thread(target=run)
    t.start()
    main()
    t.join()