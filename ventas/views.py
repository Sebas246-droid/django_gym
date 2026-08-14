"""
Historial de ventas: la otra pestana del punto de venta.

Se cobra en la caja, no aqui. Y se mira por dia, porque la pregunta de quien
abre esta pantalla casi siempre es "cuanto llevo hoy" al cerrar el turno, no
"que vendi en marzo".

Antes existia tambien un alta de venta a mano: creaba una venta vacia y se le
iban pegando lineas. Sobraba, porque el punto de venta hace lo mismo mejor, y
dejaba borradores en cero que se veian en el historial como si fueran ventas.
"""

from datetime import datetime, timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView

from core.mixins import GymQuerysetMixin
from ventas.models import Venta


class VentaListView(GymQuerysetMixin, ListView):
    model = Venta
    template_name = 'ventas/venta_list.html'
    context_object_name = 'ventas'

    def get_queryset(self):
        # Un borrador es el carrito de alguien en la caja: ni se cobro ni toco
        # el inventario, asi que no es una venta y no va en el historial.
        qs = (
            super()
            .get_queryset()
            .filter(estado=Venta.CONFIRMADA, fecha__date=self.dia)
            .select_related('cliente', 'sucursal', 'usuario')
            .order_by('-fecha')
        )
        if self.sucursal_vista is not None:
            qs = qs.filter(sucursal=self.sucursal_vista)
        return qs

    @cached_property
    def dia(self):
        """El dia que se mira. Una fecha ilegible en la url no rompe: es hoy."""
        try:
            return datetime.strptime(self.request.GET['dia'], '%Y-%m-%d').date()
        except (KeyError, ValueError):
            return timezone.localdate()

    @cached_property
    def sucursal_vista(self):
        """
        De que sede es el corte. None significa todas juntas.

        Por omision se abre en la sede de quien mira, porque este corte es lo
        que se compara contra el efectivo del cajon y ese cajon es de una sola
        caja. Antes salia la suma de todo el gimnasio: con dos sucursales, el
        de Norte cuadraba su cajon contra un total que incluia a Centro y le
        aparecia un faltante que no existia.

        Con `?sucursal=todas` se ve el gimnasio completo, que es lo que quiere
        el dueno. Y un gimnasio de una sola sede no nota nada de esto.
        """
        pedida = self.request.GET.get('sucursal', '')
        if pedida == 'todas':
            return None
        if pedida.isdigit():
            elegida = self.sucursales.filter(pk=pedida).first()
            if elegida:
                return elegida
        return self.sucursal_de_trabajo

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        cobradas = self.get_queryset()

        resumen = cobradas.aggregate(total=Sum('total'), tickets=Count('pk'))
        # El corte por metodo es lo que se compara contra el efectivo en el cajon.
        #
        # El order_by() vacio no sobra: el listado viene ordenado por fecha, y
        # esa fecha se cuela en el GROUP BY. Con eso el agrupado devuelve un
        # renglon por venta en vez de uno por metodo, y el diccionario se queda
        # con el importe de la ultima. Tres cobros de 100 en efectivo salian
        # como "Efectivo 100" al lado de un "Cobrado 300".
        por_metodo = {
            fila['metodo_pago']: fila['suma']
            for fila in cobradas.order_by()
            .values('metodo_pago')
            .annotate(suma=Sum('total'))
        }

        ctx.update({
            'dia': self.dia,
            'es_hoy': self.dia == hoy,
            'dia_anterior': self.dia - timedelta(days=1),
            # Adelantarse a manana no tiene sentido: no hay nada cobrado ahi.
            'dia_siguiente': self.dia + timedelta(days=1) if self.dia < hoy else None,
            'hoy': hoy,
            'total_dia': resumen['total'] or 0,
            'tickets': resumen['tickets'],
            'metodos': [
                (etiqueta, por_metodo.get(clave, 0))
                for clave, etiqueta in Venta.METODOS_PAGO
            ],
            'sucursales': self.sucursales,
            'sucursal_vista': self.sucursal_vista,
            # El selector solo estorba en un gimnasio de una sola sede.
            'varias_sucursales': self.sucursales.count() > 1,
            # Para que las flechas de dia no tiren la sucursal elegida.
            'param_sucursal': (
                f'{self.sucursal_vista.pk}' if self.sucursal_vista else 'todas'
            ),
        })
        return ctx


class VentaDetailView(GymQuerysetMixin, DetailView):
    """El ticket, ya cobrado. Solo de lectura."""

    model = Venta
    template_name = 'ventas/venta_detail.html'
    context_object_name = 'venta'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['detalles'] = self.object.detalles.select_related('producto', 'membresia')
        return ctx
