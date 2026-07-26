from django.db import models
from django.utils import timezone

from core.models import GymModel, TimeStampedModel


class CategoriaProducto(GymModel):
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoria de producto'
        verbose_name_plural = 'Categorias de productos'

    def __str__(self):
        return self.nombre


class Producto(GymModel):
    """Catalogo de productos. NO guarda stock."""

    categoria = models.ForeignKey(
        CategoriaProducto, on_delete=models.PROTECT, related_name='productos'
    )
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=150)
    marca = models.CharField(max_length=100, blank=True)
    foto = models.ImageField(upload_to='productos/', blank=True, null=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['nombre']
        unique_together = [('gym', 'codigo')]
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'

    def stock_en(self, sucursal):
        inv = self.inventarios.filter(sucursal=sucursal).first()
        return inv.stock if inv else 0


class InventarioSucursal(TimeStampedModel):
    """Stock por sucursal. Permite multiples sucursales sin duplicar productos."""

    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name='inventarios'
    )
    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.CASCADE, related_name='inventarios'
    )
    stock = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=0)

    class Meta:
        ordering = ['producto__nombre']
        unique_together = [('producto', 'sucursal')]
        verbose_name = 'Inventario por sucursal'
        verbose_name_plural = 'Inventarios por sucursal'

    def __str__(self):
        return f'{self.producto} @ {self.sucursal}: {self.stock}'

    @property
    def bajo_minimo(self):
        return self.stock <= self.stock_minimo

    @classmethod
    def mover(cls, producto, sucursal, cantidad):
        """Suma (compra) o resta (venta) stock de forma atomica."""
        inv, _ = cls.objects.get_or_create(producto=producto, sucursal=sucursal)
        cls.objects.filter(pk=inv.pk).update(stock=models.F('stock') + cantidad)
        inv.refresh_from_db()
        return inv


class Proveedor(GymModel):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'

    def __str__(self):
        return self.nombre


class Compra(GymModel):
    """Cabecera de compras. Al confirmar suma stock a la sucursal."""

    BORRADOR = 'borrador'
    CONFIRMADA = 'confirmada'
    ESTADOS = [(BORRADOR, 'Borrador'), (CONFIRMADA, 'Confirmada')]

    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, related_name='compras'
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, related_name='compras'
    )
    usuario = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='compras', null=True
    )
    fecha = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=BORRADOR)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'

    def __str__(self):
        return f'Compra #{self.pk} - {self.proveedor}'

    def recalcular_total(self):
        total = sum(d.subtotal for d in self.detalles.all())
        Compra.objects.filter(pk=self.pk).update(total=total)
        self.total = total
        return total

    def confirmar(self):
        """Aplica el movimiento de inventario una sola vez."""
        if self.estado == self.CONFIRMADA:
            return False
        for detalle in self.detalles.all():
            InventarioSucursal.mover(detalle.producto, self.sucursal, detalle.cantidad)
        self.estado = self.CONFIRMADA
        self.recalcular_total()
        self.save(update_fields=['estado', 'updated_at'])
        return True


class CompraDetalle(TimeStampedModel):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name='compras_detalle'
    )
    cantidad = models.PositiveIntegerField(default=1)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Detalle de compra'
        verbose_name_plural = 'Detalles de compra'

    def __str__(self):
        return f'{self.producto} x{self.cantidad}'

    @property
    def subtotal(self):
        return self.cantidad * self.precio
