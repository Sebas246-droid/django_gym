from django.db import models
from django.utils.text import slugify


class ActivoQuerySet(models.QuerySet):
    """Soft delete: nunca borramos, solo marcamos activo=False."""

    def activos(self):
        return self.filter(activo=True)

    def del_gym(self, gym):
        return self.filter(gym=gym)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GymModel(TimeStampedModel):
    """
    Modelo base para toda entidad de negocio del SaaS.
    Garantiza aislamiento por gym_id y soft delete.
    """

    gym = models.ForeignKey('core.Gym', on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)

    objects = ActivoQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        self.activo = False
        self.save(update_fields=['activo', 'updated_at'])

    def unique_error_message(self, model_class, unique_check):
        """
        Los datos siempre viven dentro de un gym: nombrarlo en el error solo
        confunde. 'Ya existe un producto con ese Gym y Codigo' se lee mal
        cuando quien lo ve nunca eligio un gym.
        """
        if 'gym' in unique_check and len(unique_check) > 1:
            unique_check = tuple(f for f in unique_check if f != 'gym')
        return super().unique_error_message(model_class, unique_check)


class Plan(TimeStampedModel):
    """Características disponibles para cada cliente del SaaS."""

    nombre = models.CharField(max_length=80, unique=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usuarios_max = models.PositiveIntegerField(default=1)
    clientes_max = models.PositiveIntegerField(default=50)
    sucursales_max = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)

    objects = ActivoQuerySet.as_manager()

    class Meta:
        ordering = ['precio']
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'

    def __str__(self):
        return self.nombre


class Gym(TimeStampedModel):
    """El cliente del SaaS."""

    MONEDAS = [
        ('MXN', 'Peso mexicano'),
        ('USD', 'Dolar'),
        ('EUR', 'Euro'),
        ('COP', 'Peso colombiano'),
        ('ARS', 'Peso argentino'),
    ]

    FRASE_DEFAULT = 'Fitness para atletas de todos los dias'
    DESCRIPCION_DEFAULT = (
        'Con el mas amplio rango de equipo de cardio, fuerza y entrenamiento '
        'en grupo de la industria fitness, nuestra mision es acercarte a tus '
        'objetivos con acompanamiento profesional.'
    )

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='gyms')
    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    telefono = models.CharField(
        max_length=30,
        blank=True,
        help_text='Un solo numero: sirve de contacto y de enlace a WhatsApp. '
                  'Incluye la lada del pais, ej. 52 55 1234 5678.',
    )
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='gyms/logos/', blank=True, null=True)
    fecha_alta = models.DateField(auto_now_add=True)
    zona_horaria = models.CharField(max_length=64, default='America/Mexico_City')
    moneda = models.CharField(max_length=3, choices=MONEDAS, default='MXN')
    activo = models.BooleanField(default=True)

    # --- Sitio publico -----------------------------------------------------
    color_primario = models.CharField(
        max_length=7, default='#F5C518', help_text='Color de acento (botones, titulos).'
    )
    color_secundario = models.CharField(
        max_length=7, default='#111111', help_text='Color de fondo oscuro.'
    )
    frase_principal = models.CharField(max_length=160, blank=True)
    descripcion = models.TextField(blank=True)
    portada = models.ImageField(upload_to='gyms/portadas/', blank=True, null=True)
    sitio_publico = models.BooleanField(
        default=True, help_text='Muestra la pagina publica del gimnasio.'
    )

    objects = ActivoQuerySet.as_manager()

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Gimnasio'
        verbose_name_plural = 'Gimnasios'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre)[:130] or 'gym'
            slug = base
            n = 2
            while Gym.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # --- Sitio publico ----------------------------------------------------
    @staticmethod
    def _rgb(hex_color):
        valor = (hex_color or '').lstrip('#')
        if len(valor) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(valor[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    @property
    def color_primario_rgb(self):
        """Para usar el acento con transparencia en CSS: rgba(var(--acento-rgb), .1)."""
        return ', '.join(str(c) for c in self._rgb(self.color_primario))

    @property
    def color_primario_texto(self):
        """Texto legible encima del acento, sea claro u oscuro el color elegido."""
        r, g, b = self._rgb(self.color_primario)
        luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return '#0B0B0F' if luminancia > 0.6 else '#FFFFFF'

    @property
    def frase(self):
        return self.frase_principal or self.FRASE_DEFAULT

    @property
    def texto(self):
        return self.descripcion or self.DESCRIPCION_DEFAULT

    @property
    def whatsapp_url(self):
        """El mismo telefono de contacto sirve para el boton de WhatsApp."""
        numero = ''.join(c for c in self.telefono if c.isdigit())
        return f'https://wa.me/{numero}' if numero else ''

    # --- Limites del plan -------------------------------------------------
    def puede_crear_sucursal(self):
        return self.sucursales.filter(activo=True).count() < self.plan.sucursales_max

    def puede_crear_usuario(self):
        return self.users.filter(is_active=True).count() < self.plan.usuarios_max

    def puede_crear_cliente(self):
        return self.clientes.filter(activo=True).count() < self.plan.clientes_max


class Sucursal(GymModel):
    """Cada gimnasio puede tener una o varias sucursales segun su plan."""

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='sucursales')
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    responsable = models.CharField(max_length=120, blank=True)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text='Ej. 19.432608',
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text='Ej. -99.133209',
    )

    class Meta:
        ordering = ['nombre']
        unique_together = [('gym', 'nombre')]
        verbose_name = 'Sucursal'
        verbose_name_plural = 'Sucursales'

    def __str__(self):
        return self.nombre

    @property
    def tiene_mapa(self):
        return self.latitud is not None and self.longitud is not None

    @property
    def mapa_embed_url(self):
        """Mapa de OpenStreetMap, sin API key."""
        if not self.tiene_mapa:
            return ''
        lat, lon = float(self.latitud), float(self.longitud)
        d = 0.004
        bbox = f'{lon - d},{lat - d},{lon + d},{lat + d}'
        return (
            f'https://www.openstreetmap.org/export/embed.html'
            f'?bbox={bbox}&layer=mapnik&marker={lat},{lon}'
        )

    @property
    def mapa_url(self):
        if not self.tiene_mapa:
            return ''
        return f'https://www.openstreetmap.org/?mlat={self.latitud}&mlon={self.longitud}#map=17'


class GymImagen(GymModel):
    """Galeria de la pagina publica: el gimnasio sube sus propias fotos."""

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='imagenes')
    imagen = models.ImageField(upload_to='gyms/galeria/')
    titulo = models.CharField(max_length=120, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']
        verbose_name = 'Imagen del sitio'
        verbose_name_plural = 'Imagenes del sitio'

    def __str__(self):
        return self.titulo or f'Imagen {self.pk}'
