"""
Lo minimo de la API de Telegram para este bot.

Es REST plano sobre HTTPS, asi que se habla con urllib y no hace falta sumar
una dependencia. Solo se usan tres llamadas: mandar mensaje, registrar el
webhook y averiguar el nombre del bot.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

API = 'https://api.telegram.org/bot{token}/{metodo}'
TIEMPO_LIMITE = 10


class ErrorTelegram(Exception):
    """La llamada llego a Telegram y Telegram la rechazo."""

    def __init__(self, descripcion, codigo=None):
        super().__init__(descripcion)
        self.descripcion = descripcion
        self.codigo = codigo

    @property
    def bloqueado(self):
        """403: el socio bloqueo al bot. No sirve reintentar."""
        return self.codigo == 403


def llamar(token, metodo, **parametros):
    cuerpo = json.dumps(parametros).encode()
    peticion = Request(
        API.format(token=token, metodo=metodo),
        data=cuerpo,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urlopen(peticion, timeout=TIEMPO_LIMITE) as respuesta:
            return json.loads(respuesta.read())['result']
    except HTTPError as exc:
        detalle = {}
        try:
            detalle = json.loads(exc.read())
        except (ValueError, OSError):
            pass
        raise ErrorTelegram(
            detalle.get('description', str(exc)), codigo=exc.code
        ) from exc
    except URLError as exc:
        raise ErrorTelegram(f'No se pudo contactar a Telegram: {exc.reason}') from exc


def teclado(filas):
    """
    Menu de botones. Se usa el teclado normal y no los botones en linea porque
    al tocarlo manda el texto como un mensaje mas: un solo camino de entrada.
    """
    return {
        'keyboard': [[{'text': texto} for texto in fila] for fila in filas],
        'resize_keyboard': True,
    }


def enviar(token, chat_id, texto, botones=None):
    parametros = {'chat_id': chat_id, 'text': texto, 'parse_mode': 'HTML'}
    if botones is not None:
        parametros['reply_markup'] = teclado(botones)
    return llamar(token, 'sendMessage', **parametros)


def registrar_webhook(token, url, secreto):
    return llamar(
        token,
        'setWebhook',
        url=url,
        secret_token=secreto,
        # Solo interesan los mensajes: sin esto Telegram manda de todo.
        allowed_updates=['message'],
    )


def quitar_webhook(token):
    return llamar(token, 'deleteWebhook')


def datos_del_bot(token):
    return llamar(token, 'getMe')
