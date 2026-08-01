"""
Historial de ventas. Cobrar se hace en el punto de venta, no aqui.

Antes existia tambien un alta de venta a mano: creaba una venta vacia y se le
iban pegando lineas. Sobraba, porque el punto de venta hace lo mismo mejor, y
dejaba borradores en cero que se veian en el historial como si fueran ventas.
"""

from django.views.generic import DetailView, ListView

from core.mixins import GymQuerysetMixin
from ventas.models import Venta


class VentaListView(GymQuerysetMixin, ListView):
    model = Venta
    template_name = 'ventas/venta_list.html'
    context_object_name = 'ventas'
    paginate_by = 30

    def get_queryset(self):
        # Un borrador es el carrito de alguien en la caja: ni se cobro ni toco
        # el inventario, asi que no es una venta y no va en el historial.
        return (
            super()
            .get_queryset()
            .filter(estado=Venta.CONFIRMADA)
            .select_related('cliente', 'sucursal', 'usuario')
        )


class VentaDetailView(GymQuerysetMixin, DetailView):
    """El ticket, ya cobrado. Solo de lectura."""

    model = Venta
    template_name = 'ventas/venta_detail.html'
    context_object_name = 'venta'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['detalles'] = self.object.detalles.select_related('producto', 'membresia')
        return ctx
