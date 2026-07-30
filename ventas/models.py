from django.db import models
from django.utils import timezone

from core.models import GymModel, TimeStampedModel
from inventario.models import Movimiento, Producto


class Venta(GymModel):
    """Venta de mostrador. Al confirmar descuenta stock de la sucursal."""

    BORRADOR = 'borrador'
    CONFIRMADA = 'confirmada'
    ESTADOS = [(BORRADOR, 'Borrador'), (CONFIRMADA, 'Confirmada')]

    METODOS_PAGO = [
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia'),
    ]

    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, related_name='ventas'
    )
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        related_name='ventas',
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='ventas', null=True
    )
    fecha = models.DateTimeField(default=timezone.now)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metodo_pago = models.CharField(
        max_length=15, choices=METODOS_PAGO, default='efectivo'
    )
    estado = models.CharField(max_length=10, choices=ESTADOS, default=BORRADOR)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'

    def __str__(self):
        return f'Venta #{self.pk}'

    def recalcular_total(self):
        subtotal = sum(d.subtotal for d in self.detalles.all())
        total = max(subtotal - self.descuento, 0)
        Venta.objects.filter(pk=self.pk).update(subtotal=subtotal, total=total)
        self.subtotal, self.total = subtotal, total
        return total

    @property
    def piezas(self):
        return sum(d.cantidad for d in self.detalles.all())

    def stock_suficiente(self):
        """Los detalles sin stock disponible. Las membresias no gastan stock."""
        faltantes = []
        for detalle in self.detalles.select_related('producto').filter(
            producto__isnull=False
        ):
            if detalle.producto.stock_en(self.sucursal) < detalle.cantidad:
                faltantes.append(detalle)
        return faltantes

    @property
    def tiene_membresias(self):
        return self.detalles.filter(membresia__isnull=False).exists()

    def confirmar(self):
        if self.estado == self.CONFIRMADA:
            return False, 'La venta ya estaba confirmada.'
        if not self.detalles.exists():
            return False, 'La venta no tiene nada que cobrar.'
        # Sin socio no hay a quien asignarle la membresia que se esta cobrando.
        if self.tiene_membresias and self.cliente_id is None:
            return False, 'Elige al socio: la venta lleva una membresia.'
        faltantes = self.stock_suficiente()
        if faltantes:
            nombres = ', '.join(str(d.producto) for d in faltantes)
            return False, f'Sin stock suficiente: {nombres}'

        for detalle in self.detalles.select_related('producto', 'membresia'):
            if detalle.es_membresia:
                self._asignar_membresia(detalle)
            else:
                # Sale por el libro de movimientos, no tocando el stock
                # directo: si no, la venta no aparece en el historial y las
                # existencias cambian sin que nada explique por que.
                Movimiento.registrar(
                    producto=detalle.producto,
                    sucursal=self.sucursal,
                    tipo=Movimiento.SALIDA,
                    motivo=Movimiento.VENTA,
                    cantidad=detalle.cantidad,
                    precio=detalle.precio,
                    usuario=self.usuario,
                    venta_detalle=detalle,
                )

        self.estado = self.CONFIRMADA
        self.recalcular_total()
        self.save(update_fields=['estado', 'updated_at'])
        return True, 'Venta confirmada.'

    def _asignar_membresia(self, detalle):
        """
        Le da al socio la membresia que acaba de pagar. Una linea con cantidad
        mayor a uno son periodos seguidos, encadenados uno tras otro.
        """
        from clientes.models import ClienteMembresia

        for _ in range(detalle.cantidad):
            ClienteMembresia.objects.create(
                gym=self.gym,
                cliente=self.cliente,
                membresia=detalle.membresia,
                inicio=self.cliente.inicio_siguiente_membresia,
                precio=detalle.precio,
                metodo_pago=self.metodo_pago,
                fecha_pago=self.fecha,
                usuario=self.usuario,
                venta_detalle=detalle,
            )


class VentaDetalle(TimeStampedModel):
    """
    Una linea de la venta: un producto o una membresia, nunca las dos.

    Una membresia tambien es una venta, asi que se cobra por aqui en vez de
    llevar su dinero aparte. La diferencia es lo que pasa al confirmar: el
    producto descuenta stock y la membresia se le asigna al socio.
    """

    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='ventas_detalle',
        null=True,
        blank=True,
    )
    membresia = models.ForeignKey(
        'clientes.Membresia',
        on_delete=models.PROTECT,
        related_name='ventas_detalle',
        null=True,
        blank=True,
    )
    cantidad = models.PositiveIntegerField(default=1)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'
        constraints = [
            # La base tambien lo exige: una linea sin nada, o con las dos cosas,
            # no significa nada y romperia el cobro.
            models.CheckConstraint(
                condition=(
                    models.Q(producto__isnull=False, membresia__isnull=True)
                    | models.Q(producto__isnull=True, membresia__isnull=False)
                ),
                name='detalle_producto_o_membresia',
            )
        ]

    def __str__(self):
        return f'{self.concepto} x{self.cantidad}'

    @property
    def concepto(self):
        return self.producto or self.membresia

    @property
    def es_membresia(self):
        return self.membresia_id is not None

    @property
    def subtotal(self):
        return self.cantidad * self.precio
