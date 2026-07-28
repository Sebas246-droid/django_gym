"""
Bot de Telegram: la linea de comunicacion entre el gimnasio y sus socios.

Cada gimnasio pone su propio bot (creado en BotFather), asi que el token vive
por gimnasio y el webhook trae el slug en la URL. Lo que el socio consulta sale
de los mismos modelos que usa el panel; aqui solo se guarda lo que hace falta
para saber quien esta del otro lado y en que punto de una conversacion va.
"""

import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

#: Alfabeto sin caracteres que se confunden al dictarlos (O/0, I/1, etc.).
ALFABETO_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


class BotTelegram(TimeStampedModel):
    """Bot propio de un gimnasio. El token lo genera BotFather."""

    gym = models.OneToOneField('core.Gym', on_delete=models.CASCADE, related_name='bot')
    token = models.CharField(
        max_length=100,
        help_text='El que te da BotFather al crear el bot, con el formato 123456:ABC-DEF...',
    )
    # Telegram lo devuelve en cada webhook: es lo que prueba que la llamada
    # viene de Telegram y no de cualquiera que adivine la URL.
    secreto = models.CharField(max_length=64, blank=True)
    usuario_bot = models.CharField(
        max_length=64, blank=True, help_text='Nombre del bot, por ejemplo mi_gimnasio_bot.'
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Bot de Telegram'
        verbose_name_plural = 'Bots de Telegram'

    def __str__(self):
        return f'Bot de {self.gym}'

    def save(self, *args, **kwargs):
        if not self.secreto:
            self.secreto = secrets.token_urlsafe(32)[:64]
        super().save(*args, **kwargs)


class ClienteTelegram(TimeStampedModel):
    """
    Un socio vinculado con su chat de Telegram.

    Guarda tambien en que punto va una conversacion de varios pasos, como la
    calculadora: Telegram no tiene sesion, cada mensaje llega suelto.
    """

    cliente = models.OneToOneField(
        'clientes.Cliente', on_delete=models.CASCADE, related_name='telegram'
    )
    chat_id = models.BigIntegerField(db_index=True)
    nombre_telegram = models.CharField(max_length=150, blank=True)
    #: Que se esta esperando del socio ahora. Vacio = no hay nada a medias.
    paso = models.CharField(max_length=30, blank=True)
    #: Respuestas parciales del paso a paso en curso.
    datos = models.JSONField(default=dict, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Socio en Telegram'
        verbose_name_plural = 'Socios en Telegram'

    def __str__(self):
        return f'{self.cliente} en Telegram'

    def limpiar_paso(self):
        self.paso = ''
        self.datos = {}
        self.save(update_fields=['paso', 'datos', 'updated_at'])


class CodigoVinculacion(TimeStampedModel):
    """
    Codigo de un solo uso para atar un chat a un socio.

    No sirve pedir el numero de socio: son consecutivos desde 1000 y cualquiera
    adivinaria el del vecino, quedandose con sus pagos y sus asistencias.
    """

    VALIDEZ_MINUTOS = 15

    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.CASCADE, related_name='codigos_telegram'
    )
    codigo = models.CharField(max_length=8, unique=True, db_index=True)
    expira_en = models.DateTimeField()
    usado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Codigo de vinculacion'
        verbose_name_plural = 'Codigos de vinculacion'

    def __str__(self):
        return f'{self.codigo} para {self.cliente}'

    @property
    def vigente(self):
        return self.usado_en is None and self.expira_en > timezone.now()

    @classmethod
    def emitir(cls, cliente):
        """Un codigo vigente por socio: pedir otro invalida el anterior."""
        cls.objects.filter(cliente=cliente, usado_en__isnull=True).delete()
        return cls.objects.create(
            cliente=cliente,
            codigo=''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(6)),
            expira_en=timezone.now() + timedelta(minutes=cls.VALIDEZ_MINUTOS),
        )


class MedidaCorporal(TimeStampedModel):
    """
    Peso y estatura para la calculadora. Se guarda el historico en vez de
    sobrescribir: ver la evolucion es justamente lo que le sirve al socio.
    """

    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.CASCADE, related_name='medidas'
    )
    peso_kg = models.DecimalField(max_digits=5, decimal_places=1)
    estatura_cm = models.PositiveSmallIntegerField()
    fecha = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['-fecha', '-created_at']
        verbose_name = 'Medida corporal'
        verbose_name_plural = 'Medidas corporales'

    def __str__(self):
        return f'{self.cliente}: {self.peso_kg} kg el {self.fecha}'
