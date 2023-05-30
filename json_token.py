import json
from config import PATH_TO_FILE 


# функция для сохранения токена и chat_id в файле json
def save_data(token, chat_id):
    # Загружаем данные из файла json, если файл уже существует
    try:
        with open(PATH_TO_FILE, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    # проверяем, нет ли таких значений token и chat_id в словаре
    if token not in data.values() and chat_id not in data.values():
        data[token] = chat_id
    # проверяем есть ли такой chat id в словаре для смены аккаунта
    elif chat_id in data.values():
        # находим все пары, где значение = chat_id
        keys_to_remove = [key for key, value in data.items() if value == chat_id]
        # удаляем все эти пары
        for key in keys_to_remove:
            del data[key]
        # записываем новую
        data[token] = chat_id

    # сохраняем данные в файле json
    with open(PATH_TO_FILE, 'w') as f:
        json.dump(data, f)

# функция для загрузки chat_id по токену из файла json
def load_chat_id(token):
    # загружаем данные из файла json
    with open(PATH_TO_FILE, 'r') as f:
        data = json.load(f)

    # ищем chat_id для заданного токена, если такой токен есть
    if token in data:
        return data[token]

    # усли токен не найден, возвращаем None
    return None

# функция для загрузки токена по chat_id из файла json
def load_token(chat_id):
    # загружаем данные из файла json
    with open(PATH_TO_FILE, 'r') as f:
        data = json.load(f)

    # ищем токен для заданного chat_id, если такой chat_id есть
    for token, c_id in data.items():
        if c_id == chat_id:
            return token

    # если chat_id не найден, возвращаем None
    return None
