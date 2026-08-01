from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.db.models.functions import Cast
from django.utils import timezone

from core.archivos import RutaPorGym, validar_comprobante
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


#: Cuanto entrena a la semana. Multiplica el gasto en reposo para estimar el
#: consumo diario, asi que el valor guardado no cambia aunque cambie el texto.
NIVELES_ACTIVIDAD = [
    ('sedentario', 'Nada o casi nada'),
    ('ligero', '1 a 3 dias por semana'),
    ('moderado', '3 a 5 dias por semana'),
    ('intenso', '6 o 7 dias por semana'),
]


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
    # Datos estables que necesita la calculadora de calorias. Capturarlos al dar
    # de alta ahorra preguntas despues: el peso es lo unico que cambia seguido.
    estatura_cm = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='En centimetros, por ejemplo 175.'
    )
    nivel_actividad = models.CharField(
        max_length=12,
        choices=NIVELES_ACTIVIDAD,
        blank=True,
        help_text='Cuanto entrena a la semana.',
    )
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

    #: Cuantas veces se recalcula el numero si otra alta se adelanto.
    INTENTOS_NUMERO = 5

    def save(self, *args, **kwargs):
        if self.numero_usuario:
            return super().save(*args, **kwargs)

        # Calcular el numero y guardarlo son dos pasos, asi que dos altas a la
        # vez pueden sacar el mismo. Quien decide es el indice unico de la base:
        # si rebota, se recalcula y se reintenta.
        for intento in range(self.INTENTOS_NUMERO):
            self.numero_usuario = self.siguiente_numero(self.gym_id)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if not self._numero_ocupado() or intento == self.INTENTOS_NUMERO - 1:
                    raise  # el choque fue por otra cosa, o ya se intento de mas
                self.numero_usuario = ''

    def _numero_ocupado(self):
        """Distingue el choque de numero de cualquier otro error de integridad."""
        return (
            Cliente.objects.filter(
                gym_id=self.gym_id, numero_usuario=self.numero_usuario
            )
            .exclude(pk=self.pk)
            .exists()
        )

    @staticmethod
    def siguiente_numero(gym_id):
        """
        Numeros de 4 digitos a partir del 1000, consecutivos por gimnasio.

        Los de las bajas no se reciclan: el numero identifica a una persona en
        el historial de asistencias y reusarlo mezclaria a dos.
        """
        # El maximo lo saca la base. Hay que compararlos como numeros, no como
        # texto, o '999' saldria mayor que '1000'.
        mayor = (
            Cliente.objects.filter(gym_id=gym_id, numero_usuario__regex=r'^\d+$')
            .annotate(valor=Cast('numero_usuario', models.IntegerField()))
            .aggregate(mayor=models.Max('valor'))['mayor']
        )
        return str(1000 if mayor is None else mayor + 1)

    @property
    def membresia_vigente(self):
        return (
            ClienteMembresia.vigentes_en()
            .filter(cliente=self)
            .order_by('-fin')
            .first()
        )

    @property
    def esta_al_corriente(self):
        return self.membresia_vigente is not None

    @property
    def ultima_membresia(self):
        """
        La mas reciente aunque este vencida: sirve para avisar en el acceso.
        Una cancelada no cuenta, o el aviso hablaria de algo que se deshizo.
        """
        return (
            self.membresias.filter(activo=True)
            .exclude(estado=ClienteMembresia.CANCELADA)
            .order_by('-fin')
            .first()
        )

    @property
    def dias_restantes(self):
        vigente = self.membresia_vigente
        if not vigente:
            return None
        return (vigente.fin - timezone.localdate()).days

    @property
    def inicio_siguiente_membresia(self):
        """
        Desde cuando corre la siguiente membresia.

        Si renueva antes de que se le acabe la actual, arranca al dia siguiente
        de esa: empezar hoy le borraria los dias que le quedaban pagados.
        """
        vigente = self.membresia_vigente
        hoy = timezone.localdate()
        if vigente is None:
            return hoy
        return max(vigente.fin + timedelta(days=1), hoy)


class ClienteMembresia(GymModel):
    """Historial completo de compras de membresias (incluye el cobro)."""

    VIGENTE = 'vigente'
    VENCIDA = 'vencida'
    CANCELADA = 'cancelada'
    ESTADOS = [
        (VIGENTE, 'Vigente'),
        (VENCIDA, 'Vencida'),
        (CANCELADA, 'Cancelada'),
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
    # Foto del ticket o PDF de la transferencia. Sirve para aclarar un cobro
    # que el socio reclama meses despues, cuando ya nadie se acuerda.
    comprobante = models.FileField(
        upload_to=RutaPorGym('comprobantes'),
        blank=True,
        null=True,
        validators=validar_comprobante,
        help_text='Foto o PDF del pago. Opcional.',
    )
    observaciones = models.TextField(blank=True)
    usuario = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='membresias_cobradas',
        null=True,
    )
    # Puesto cuando se cobro en el punto de venta. Ese dinero ya esta contado
    # en la venta, asi que sumarlo otra vez aqui duplicaria los ingresos.
    # Es de uno a varios: una linea con cantidad 2 son dos periodos seguidos.
    venta_detalle = models.ForeignKey(
        'ventas.VentaDetalle',
        on_delete=models.SET_NULL,
        related_name='membresias_asignadas',
        null=True,
        blank=True,
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

    @classmethod
    def vigentes_en(cls, dia=None):
        """
        Las que de verdad dan acceso ese dia.

        Una cancelada tiene fechas que siguen abarcando hoy, asi que sin
        excluirla el socio entraria al gimnasio con una membresia deshecha.
        """
        dia = dia or timezone.localdate()
        return cls.objects.filter(
            activo=True, inicio__lte=dia, fin__gte=dia
        ).exclude(estado=cls.CANCELADA)

    @classmethod
    def cobradas_aparte(cls, gym, dia):
        """
        Las cobradas desde su propia pantalla, que son las unicas cuyo dinero
        no esta ya dentro de una Venta. Contar tambien las del punto de venta
        duplicaria los ingresos del dia.
        """
        return cls.objects.filter(
            gym=gym, activo=True, fecha_pago__date=dia, venta_detalle__isnull=True
        ).exclude(estado=cls.CANCELADA)

    def save(self, *args, **kwargs):
        if not self.fin:
            self.fin = self.inicio + timedelta(days=self.membresia.duracion_dias)
        if self.estado == self.VIGENTE and self.fin < timezone.localdate():
            self.estado = self.VENCIDA
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
