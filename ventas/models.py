from django.db import models
from django.utils import timezone

from core.models import GymModel, TimeStampedModel
from inventario.models import InventarioSucursal, Producto


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
        """Devuelve la lista de detalles que no tienen stock disponible."""
        faltantes = []
        for detalle in self.detalles.select_related('producto'):
            if detalle.producto.stock_en(self.sucursal) < detalle.cantidad:
                faltantes.append(detalle)
        return faltantes

    def confirmar(self):
        if self.estado == self.CONFIRMADA:
            return False, 'La venta ya estaba confirmada.'
        if not self.detalles.exists():
            return False, 'La venta no tiene productos.'
        faltantes = self.stock_suficiente()
        if faltantes:
            nombres = ', '.join(str(d.producto) for d in faltantes)
            return False, f'Sin stock suficiente: {nombres}'
        for detalle in self.detalles.all():
            InventarioSucursal.mover(detalle.producto, self.sucursal, -detalle.cantidad)
        self.estado = self.CONFIRMADA
        self.recalcular_total()
        self.save(update_fields=['estado', 'updated_at'])
        return True, 'Venta confirmada.'


class VentaDetalle(TimeStampedModel):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name='ventas_detalle'
    )
    cantidad = models.PositiveIntegerField(default=1)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'

    def __str__(self):
        return f'{self.producto} x{self.cantidad}'

    @property
    def subtotal(self):
        return self.cantidad * self.precio
