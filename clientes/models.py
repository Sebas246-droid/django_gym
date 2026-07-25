from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.models import GymModel


class Membresia(GymModel):
    """Catalogo de membresias del gimnasio."""

    nombre = models.CharField(max_length=120)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duracion_dias = models.PositiveIntegerField(default=30)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Membresia'
        verbose_name_plural = 'Membresias'

    def __str__(self):
        return f'{self.nombre} ({self.duracion_dias} dias)'


class Cliente(GymModel):
    SEXOS = [('M', 'Masculino'), ('F', 'Femenino'), ('O', 'Otro')]

    gym = models.ForeignKey(
        'core.Gym', on_delete=models.CASCADE, related_name='clientes'
    )
    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, related_name='clientes'
    )
    numero_usuario = models.CharField(
        max_length=5,
        blank=True,
        db_index=True,
        help_text='Numero que teclea el cliente en el check-in. Se asigna solo.',
    )
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    sexo = models.CharField(max_length=1, choices=SEXOS, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    foto = models.ImageField(upload_to='clientes/', blank=True, null=True)
    nombre_contacto_emergencia = models.CharField(max_length=150, blank=True)
    telefono_contacto_emergencia = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['nombre']
        unique_together = [('gym', 'numero_usuario')]
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.numero_usuario:
            self.numero_usuario = self.siguiente_numero(self.gym_id)
        super().save(*args, **kwargs)

    @staticmethod
    def siguiente_numero(gym_id):
        """Numeros de 4 digitos a partir del 1000, consecutivos por gimnasio."""
        usados = (
            Cliente.objects.filter(gym_id=gym_id)
            .exclude(numero_usuario='')
            .values_list('numero_usuario', flat=True)
        )
        numeros = [int(n) for n in usados if n.isdigit()]
        return str(max(numeros) + 1 if numeros else 1000)

    @property
    def membresia_vigente(self):
        hoy = timezone.localdate()
        return (
            self.membresias.filter(activo=True, inicio__lte=hoy, fin__gte=hoy)
            .order_by('-fin')
            .first()
        )

    @property
    def esta_al_corriente(self):
        return self.membresia_vigente is not None

    @property
    def ultima_membresia(self):
        """La mas reciente aunque este vencida: sirve para avisar en el acceso."""
        return self.membresias.filter(activo=True).order_by('-fin').first()

    @property
    def dias_restantes(self):
        vigente = self.membresia_vigente
        if not vigente:
            return None
        return (vigente.fin - timezone.localdate()).days


class ClienteMembresia(GymModel):
    """Historial completo de compras de membresias (incluye el cobro)."""

    ESTADOS = [
        ('vigente', 'Vigente'),
        ('vencida', 'Vencida'),
        ('cancelada', 'Cancelada'),
    ]
    METODOS_PAGO = [
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia'),
    ]

    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name='membresias'
    )
    membresia = models.ForeignKey(
        Membresia, on_delete=models.PROTECT, related_name='ventas'
    )
    inicio = models.DateField(default=timezone.localdate)
    fin = models.DateField(blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='vigente')
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    metodo_pago = models.CharField(
        max_length=15, choices=METODOS_PAGO, default='efectivo'
    )
    fecha_pago = models.DateTimeField(default=timezone.now)
    observaciones = models.TextField(blank=True)
    usuario = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='membresias_cobradas',
        null=True,
    )

    class Meta:
        ordering = ['-fecha_pago']
        verbose_name = 'Membresia de cliente'
        verbose_name_plural = 'Membresias de clientes'

    def __str__(self):
        return f'{self.cliente} - {self.membresia}'

    @property
    def total(self):
        return self.precio - self.descuento

    def save(self, *args, **kwargs):
        if not self.fin:
            self.fin = self.inicio + timedelta(days=self.membresia.duracion_dias)
        if self.estado == 'vigente' and self.fin < timezone.localdate():
            self.estado = 'vencida'
        super().save(*args, **kwargs)


class Asistencia(GymModel):
    """Registro de entradas y salidas."""

    ENTRADA = 'entrada'
    SALIDA = 'salida'
    TIPOS = [(ENTRADA, 'Entrada'), (SALIDA, 'Salida')]

    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, related_name='asistencias'
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name='asistencias'
    )
    usuario = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='asistencias_registradas',
        null=True,
    )
    entrenamiento = models.ForeignKey(
        'entrenamiento.Entrenamiento',
        on_delete=models.SET_NULL,
        related_name='asistencias',
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=8, choices=TIPOS, default=ENTRADA)

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Asistencia'
        verbose_name_plural = 'Asistencias'

    def __str__(self):
        return f'{self.cliente} - {self.get_tipo_display()}'
