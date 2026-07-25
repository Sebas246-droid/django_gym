"""
Punto de venta.

El carrito no vive en la sesion: es una Venta en estado borrador. Asi el
calculo del total, la validacion de stock y el descuento de inventario son
exactamente los mismos que en el resto del sistema, y si se cae el navegador
el carrito sigue ahi.
"""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from clientes.models import Cliente
from core.mixins import GymRequiredMixin
from inventario.models import CategoriaProducto, InventarioSucursal, Producto
from ventas.models import Venta, VentaDetalle


class CarritoMixin(GymRequiredMixin):
    """Da acceso al carrito abierto de quien esta atendiendo la caja."""

    @property
    def sucursal(self):
        return self.request.user.sucursal or self.gym.sucursales.filter(
            activo=True
        ).first()

    def carrito(self, crear=True):
        venta = Venta.objects.filter(
            gym=self.gym,
            usuario=self.request.user,
            estado=Venta.BORRADOR,
            activo=True,
        ).order_by('-fecha').first()
        if venta or not crear:
            return venta
        return Venta.objects.create(
            gym=self.gym,
            sucursal=self.sucursal,
            usuario=self.request.user,
        )


class POSView(CarritoMixin, TemplateView):
    """Rejilla de productos a la izquierda, carrito a la derecha."""

    template_name = 'ventas/pos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sucursal = self.sucursal
        # Abrir la caja no crea nada: el carrito nace al agregar el primer producto.
        venta = self.carrito(crear=False)

        productos = Producto.objects.filter(gym=self.gym, activo=True).select_related(
            'categoria'
        )
        q = self.request.GET.get('q', '').strip()
        categoria_id = self.request.GET.get('categoria', '')
        if q:
            productos = productos.filter(
                Q(nombre__icontains=q) | Q(codigo__icontains=q) | Q(marca__icontains=q)
            )
        if categoria_id:
            productos = productos.filter(categoria_id=categoria_id)

        # Una sola consulta para el stock de toda la rejilla
        existencias = dict(
            InventarioSucursal.objects.filter(
                sucursal=sucursal, producto__in=productos
            ).values_list('producto_id', 'stock')
        )
        for producto in productos:
            producto.stock_actual = existencias.get(producto.pk, 0)

        ctx.update({
            'productos': productos,
            'categorias': CategoriaProducto.objects.filter(gym=self.gym, activo=True),
            'q': q,
            'categoria_id': categoria_id,
            'venta': venta,
            'lineas': venta.detalles.select_related('producto') if venta else [],
            'sin_stock': venta.stock_suficiente() if venta else [],
            'sucursal': sucursal,
            'clientes': Cliente.objects.filter(gym=self.gym, activo=True),
            'menu': 'pos',
        })
        return ctx


class AgregarView(CarritoMixin, View):
    """Un toque en la tarjeta suma una pieza."""

    def post(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk, gym=self.gym, activo=True)
        venta = self.carrito()

        linea = venta.detalles.filter(producto=producto).first()
        if linea:
            linea.cantidad += 1
            linea.save(update_fields=['cantidad', 'updated_at'])
        else:
            VentaDetalle.objects.create(
                venta=venta,
                producto=producto,
                cantidad=1,
                precio=producto.precio_venta,
            )
        venta.recalcular_total()
        return redirect(self.volver_al_mismo_filtro())

    def volver_al_mismo_filtro(self):
        """Conserva busqueda y categoria, sin aceptar urls externas."""
        filtros = urlencode(
            {
                clave: self.request.POST.get(clave, '')
                for clave in ('q', 'categoria')
                if self.request.POST.get(clave)
            }
        )
        base = reverse('ventas:pos')
        return f'{base}?{filtros}' if filtros else base


class LineaView(CarritoMixin, View):
    """Mas, menos o quitar sobre una linea del carrito."""

    def post(self, request, pk):
        venta = self.carrito(crear=False)
        if not venta:
            return redirect('ventas:pos')
        linea = get_object_or_404(VentaDetalle, pk=pk, venta=venta)
        accion = request.POST.get('accion')

        if accion == 'mas':
            linea.cantidad += 1
            linea.save(update_fields=['cantidad', 'updated_at'])
        elif accion == 'menos':
            if linea.cantidad > 1:
                linea.cantidad -= 1
                linea.save(update_fields=['cantidad', 'updated_at'])
            else:
                linea.delete()
        else:
            linea.delete()

        venta.recalcular_total()
        return redirect('ventas:pos')


class CobrarView(CarritoMixin, View):
    def post(self, request):
        venta = self.carrito(crear=False)
        if not venta or not venta.detalles.exists():
            messages.error(request, 'El carrito esta vacio.')
            return redirect('ventas:pos')

        venta.metodo_pago = request.POST.get('metodo_pago', 'efectivo')
        venta.descuento = self._descuento(request.POST.get('descuento'))
        cliente_id = request.POST.get('cliente') or None
        venta.cliente = (
            Cliente.objects.filter(pk=cliente_id, gym=self.gym).first()
            if cliente_id
            else None
        )
        venta.save(update_fields=['metodo_pago', 'descuento', 'cliente', 'updated_at'])

        with transaction.atomic():
            ok, mensaje = venta.confirmar()

        if ok:
            messages.success(request, f'{mensaje} Total cobrado: {venta.total}.')
            return redirect('ventas:venta_detail', pk=venta.pk)

        messages.error(request, mensaje)
        return redirect('ventas:pos')

    @staticmethod
    def _descuento(valor):
        try:
            return max(Decimal(valor or '0'), Decimal('0'))
        except (InvalidOperation, TypeError):
            return Decimal('0')


class CancelarView(CarritoMixin, View):
    def post(self, request):
        venta = self.carrito(crear=False)
        if venta:
            venta.detalles.all().delete()
            venta.soft_delete()
            messages.info(request, 'Carrito vaciado.')
        return redirect('ventas:pos')
