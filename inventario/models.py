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


class Movimiento(GymModel):
    """
    Todo lo que entra y sale del inventario, en un solo libro.

    Antes las entradas eran compras con cabecera y lineas, y las salidas no se
    anotaban en ningun lado: la venta movia el stock directo y una merma se
    corregia a mano. Asi no habia forma de responder por que hay lo que hay.
    Ahora cada cambio de existencias deja su renglon, con su motivo.
    """

    ENTRADA = 'entrada'
    SALIDA = 'salida'
    TIPOS = [(ENTRADA, 'Entrada'), (SALIDA, 'Salida')]

    COMPRA = 'compra'
    DEVOLUCION = 'devolucion'
    VENTA = 'venta'
    MERMA = 'merma'
    AJUSTE = 'ajuste'
    MOTIVOS = [
        (COMPRA, 'Compra'),
        (DEVOLUCION, 'Devolucion de un cliente'),
        (VENTA, 'Venta'),
        (MERMA, 'Merma'),
        (AJUSTE, 'Ajuste de conteo'),
    ]
    #: Que motivos suma y cuales resta. El ajuste puede ir en las dos.
    MOTIVOS_ENTRADA = [COMPRA, DEVOLUCION, AJUSTE]
    MOTIVOS_SALIDA = [VENTA, MERMA, AJUSTE]

    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name='movimientos'
    )
    sucursal = models.ForeignKey(
        'core.Sucursal', on_delete=models.PROTECT, related_name='movimientos'
    )
    tipo = models.CharField(max_length=7, choices=TIPOS)
    motivo = models.CharField(max_length=12, choices=MOTIVOS)
    cantidad = models.PositiveIntegerField()
    #: Lo que costo la pieza en una entrada; lo que se cobro en una salida.
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='movimientos', null=True
    )
    nota = models.CharField(max_length=200, blank=True)
    #: Puesto cuando la salida la genero el punto de venta.
    venta_detalle = models.ForeignKey(
        'ventas.VentaDetalle',
        on_delete=models.SET_NULL,
        related_name='movimientos',
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-fecha', '-pk']
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'

    def __str__(self):
        return f'{self.get_tipo_display()} de {self.cantidad} {self.producto}'

    @property
    def signo(self):
        return 1 if self.tipo == self.ENTRADA else -1

    @property
    def importe(self):
        return self.cantidad * self.precio

    @classmethod
    def registrar(
        cls,
        producto,
        sucursal,
        tipo,
        motivo,
        cantidad,
        precio=None,
        usuario=None,
        nota='',
        venta_detalle=None,
    ):
        """
        Anota el movimiento y mueve las existencias. Es la unica puerta: fuera
        de aqui nadie toca el stock, o el libro dejaria de cuadrar.
        """
        if precio is None:
            precio = (
                producto.precio_compra if tipo == cls.ENTRADA else producto.precio_venta
            )

        movimiento = cls.objects.create(
            gym=producto.gym,
            producto=producto,
            sucursal=sucursal,
            tipo=tipo,
            motivo=motivo,
            cantidad=cantidad,
            precio=precio,
            usuario=usuario,
            nota=nota,
            venta_detalle=venta_detalle,
        )
        InventarioSucursal.mover(producto, sucursal, movimiento.signo * cantidad)

        # El costo del producto sigue al de la ultima compra: es el que decide
        # el margen y el que se propone la proxima vez. Dejarlo viejo hace
        # creer que se gana cuando ya no.
        if motivo == cls.COMPRA and precio != producto.precio_compra:
            producto.precio_compra = precio
            producto.save(update_fields=['precio_compra', 'updated_at'])

        return movimiento
