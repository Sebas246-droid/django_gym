"""
Webhook de Telegram y pantallas del panel para administrar el bot.

El webhook es la unica parte del sistema que atiende peticiones sin sesion, asi
que valida el secreto que Telegram devuelve en cada llamada y responde 200 pase
lo que pase: un error nuestro no debe hacer que Telegram reintente en bucle.
"""

import json
import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import UpdateView, View

from bot import telegram
from bot.conversacion import responder
from bot.forms import BotTelegramForm
from bot.models import BotTelegram, CodigoVinculacion
from clientes.models import Cliente
from core.mixins import AdminRequiredMixin, GymRequiredMixin

logger = logging.getLogger(__name__)

CABECERA_SECRETO = 'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'


@csrf_exempt
def webhook(request, slug):
    """
    Recibe los mensajes de un gimnasio. La URL trae su slug y la cabecera el
    secreto: sin los dos, la llamada no se atiende.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    bot = BotTelegram.objects.select_related('gym').filter(
        gym__slug=slug, activo=True
    ).first()
    if bot is None:
        return HttpResponse(status=404)

    if not request.META.get(CABECERA_SECRETO) or (
        request.META[CABECERA_SECRETO] != bot.secreto
    ):
        logger.warning('Webhook con secreto invalido para %s', slug)
        return HttpResponse(status=403)

    try:
        mensaje = json.loads(request.body or b'{}').get('message') or {}
    except ValueError:
        return HttpResponse(status=400)

    chat_id = (mensaje.get('chat') or {}).get('id')
    if not chat_id:
        return HttpResponse(status=200)  # updates que no son mensajes de chat

    de = mensaje.get('from') or {}
    nombre = ' '.join(filter(None, [de.get('first_name'), de.get('last_name')]))

    try:
        respuesta = responder(bot.gym, chat_id, mensaje.get('text'), nombre)
        telegram.enviar(bot.token, chat_id, respuesta.texto, respuesta.botones)
    except Exception:
        # Un 500 hace que Telegram reintente el mismo mensaje una y otra vez.
        logger.exception('Fallo atendiendo un mensaje de %s', slug)

    return HttpResponse(status=200)


# --- Panel -----------------------------------------------------------------


class BotConfigView(AdminRequiredMixin, GymRequiredMixin, UpdateView):
    """Configuracion del bot del gimnasio: pegar el token y conectarlo."""

    model = BotTelegram
    form_class = BotTelegramForm
    template_name = 'bot/configuracion.html'
    success_url = reverse_lazy('bot:configuracion')
    extra_context = {'titulo': 'Bot de Telegram'}

    def get_object(self, queryset=None):
        bot, _ = BotTelegram.objects.get_or_create(gym=self.gym)
        return bot

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['url_webhook'] = self.request.build_absolute_uri(
            reverse_lazy('bot:webhook', args=[self.gym.slug])
        )
        ctx['menu'] = 'bot'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Datos del bot guardados.')
        return super().form_valid(form)


class BotConectarView(AdminRequiredMixin, GymRequiredMixin, View):
    """Registra la URL del webhook en Telegram. Es lo que enciende el bot."""

    def post(self, request):
        bot = get_object_or_404(BotTelegram, gym=self.gym)
        if not bot.token:
            messages.error(request, 'Primero pega el token que te dio BotFather.')
            return redirect('bot:configuracion')

        url = request.build_absolute_uri(
            reverse_lazy('bot:webhook', args=[self.gym.slug])
        )
        try:
            datos = telegram.datos_del_bot(bot.token)
            telegram.registrar_webhook(bot.token, url, bot.secreto)
        except telegram.ErrorTelegram as exc:
            messages.error(request, f'Telegram rechazo la conexion: {exc.descripcion}')
            return redirect('bot:configuracion')

        bot.usuario_bot = datos.get('username', '')
        bot.activo = True
        bot.save(update_fields=['usuario_bot', 'activo', 'updated_at'])
        messages.success(
            request, f'Bot conectado. Tus socios lo encuentran como @{bot.usuario_bot}.'
        )
        return redirect('bot:configuracion')


class BotDesconectarView(AdminRequiredMixin, GymRequiredMixin, View):
    def post(self, request):
        bot = get_object_or_404(BotTelegram, gym=self.gym)
        try:
            telegram.quitar_webhook(bot.token)
        except telegram.ErrorTelegram as exc:
            messages.warning(request, f'Telegram respondio: {exc.descripcion}')
        bot.activo = False
        bot.save(update_fields=['activo', 'updated_at'])
        messages.success(request, 'Bot desconectado. Deja de recibir mensajes.')
        return redirect('bot:configuracion')


class CodigoVinculacionView(GymRequiredMixin, View):
    """
    Genera el codigo que el socio escribe en el bot. Lo da recepcion en persona:
    es lo que garantiza que el chat queda atado a quien de verdad es.
    """

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk, gym=self.gym, activo=True)
        codigo = CodigoVinculacion.emitir(cliente)
        messages.success(
            request,
            f'Codigo para {cliente.nombre}: {codigo.codigo}. '
            f'Vence en {CodigoVinculacion.VALIDEZ_MINUTOS} minutos.',
        )
        return redirect('clientes:cliente_detail', pk=cliente.pk)
