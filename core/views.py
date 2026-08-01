from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from clientes.models import Asistencia, Cliente, ClienteMembresia
from core.forms import PALETAS, GymForm, GymImagenForm, GymSitioForm, PlanForm, SucursalForm
from core.mixins import (
    AdminRequiredMixin,
    GymFormMixin,
    GymRequiredMixin,
    SoftDeleteView,
    SuperUserRequiredMixin,
)
from core.models import Gym, GymImagen, Plan, Sucursal
from inventario.models import InventarioSucursal, Producto
from ventas.models import Venta, VentaDetalle


class LandingView(DetailView):
    """Pagina publica del gimnasio. No requiere iniciar sesion."""

    model = Gym
    template_name = 'core/landing.html'
    context_object_name = 'gym'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Gym.objects.filter(activo=True, sitio_publico=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        gym = self.object
        ctx['imagenes'] = gym.imagenes.filter(activo=True)
        ctx['sucursales'] = gym.sucursales.filter(activo=True)
        ctx['clientes_total'] = gym.clientes.filter(activo=True).count()
        ctx['entrenamientos_total'] = gym.entrenamiento_set.filter(activo=True).count()
        ctx['coaches_total'] = gym.users.filter(
            is_active=True, groups__name='Entrenador'
        ).count()
        return ctx


class InicioPublicoView(View):
    """
    Raiz del sitio. Si hay sesion abierta va al tablero; si solo existe un
    gimnasio publicado se muestra su pagina; en otro caso, al login.
    """

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:dashboard')
        publicados = Gym.objects.filter(activo=True, sitio_publico=True)
        if publicados.count() == 1:
            return redirect('core:landing', slug=publicados.first().slug)
        return redirect('accounts:login')


class DashboardView(GymRequiredMixin, TemplateView):
    """
    Es la primera pantalla que ve el dueno del gimnasio cada manana y la que
    se ensena al presentar el sistema: debe responder de un vistazo cuanto
    entro hoy, cuanta gente hay dentro y a quien conviene llamar.
    """

    template_name = 'core/dashboard.html'
    extra_context = {'menu': 'dashboard'}

    # --- Grafica de area (coordenadas listas para el SVG) -----------------
    # El viewBox es ancho y bajo a proposito: el SVG escala en proporcion, y
    # esta relacion deja la grafica en unos 230px de alto en pantalla.
    ANCHO = 1200
    ALTO = 262
    MARGEN_X = 44
    TECHO = 34
    PISO = 212

    def _serie(self, valores):
        """Convierte una lista de numeros en puntos para el SVG."""
        tope = max(valores + [1])
        paso = (self.ANCHO - self.MARGEN_X * 2) / max(len(valores) - 1, 1)
        puntos = []
        for i, valor in enumerate(valores):
            x = self.MARGEN_X + paso * i
            y = self.PISO - (valor / tope) * (self.PISO - self.TECHO)
            puntos.append({'x': round(x, 1), 'y': round(y, 1), 'valor': valor})
        return puntos, tope

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        gym = self.request.user.gym
        hoy = timezone.localdate()
        ayer = hoy - timezone.timedelta(days=1)
        en_una_semana = hoy + timezone.timedelta(days=7)

        # --- Dinero de hoy, con su desglose --------------------------------
        # El desglose es por donde se cobro, no por que se vendio: una
        # membresia cobrada en caja ya viene dentro del total de esa venta.
        ventas_hoy = Venta.objects.filter(
            gym=gym, fecha__date=hoy, estado=Venta.CONFIRMADA
        )
        ingreso_mostrador = ventas_hoy.aggregate(t=Sum('total'))['t'] or 0
        cobros_hoy = ClienteMembresia.cobradas_aparte(gym, hoy)
        ingreso_membresias = sum(cm.total for cm in cobros_hoy)

        ctx['ingreso_mostrador'] = ingreso_mostrador
        ctx['ingreso_membresias'] = ingreso_membresias
        ctx['ingresos_hoy'] = ingreso_mostrador + ingreso_membresias
        ctx['ventas_hoy'] = ventas_hoy.count()
        # Aqui si cuentan todas: es cuantas se vendieron, no cuanto entro.
        ctx['membresias_vendidas_hoy'] = ClienteMembresia.objects.filter(
            gym=gym, activo=True, fecha_pago__date=hoy
        ).exclude(estado='cancelada').count()

        # Ingresos de los ultimos 7 dias, para las barras del encabezado
        barras = []
        for atras in range(6, -1, -1):
            dia = hoy - timezone.timedelta(days=atras)
            productos = (
                Venta.objects.filter(
                    gym=gym, fecha__date=dia, estado=Venta.CONFIRMADA
                ).aggregate(t=Sum('total'))['t']
                or 0
            )
            membresias = sum(
                cm.total for cm in ClienteMembresia.cobradas_aparte(gym, dia)
            )
            barras.append({'dia': dia, 'monto': productos + membresias, 'hoy': dia == hoy})
        techo = max([b['monto'] for b in barras] + [1])
        for b in barras:
            b['alto'] = max(round(b['monto'] * 100 / techo), 3)
        ctx['barras_ingreso'] = barras
        ctx['ingreso_semana'] = sum(b['monto'] for b in barras)

        # --- Actividad ------------------------------------------------------
        entradas = Asistencia.objects.filter(gym=gym, tipo=Asistencia.ENTRADA)
        ctx['asistencias_hoy'] = entradas.filter(fecha_hora__date=hoy).count()
        ctx['asistencias_ayer'] = entradas.filter(fecha_hora__date=ayer).count()
        ctx['variacion_entradas'] = ctx['asistencias_hoy'] - ctx['asistencias_ayer']

        # Quien sigue dentro: su ultimo movimiento de hoy fue una entrada
        movimientos = Asistencia.objects.filter(
            gym=gym, fecha_hora__date=hoy
        ).order_by('fecha_hora')
        ultimo_por_cliente = {}
        for mov in movimientos:
            ultimo_por_cliente[mov.cliente_id] = mov.tipo
        ctx['dentro_ahora'] = sum(
            1 for tipo in ultimo_por_cliente.values() if tipo == Asistencia.ENTRADA
        )

        # Grafica de area: entradas de los ultimos 7 dias
        dias = [hoy - timezone.timedelta(days=atras) for atras in range(6, -1, -1)]
        conteos = [entradas.filter(fecha_hora__date=dia).count() for dia in dias]
        puntos, tope = self._serie(conteos)
        for punto, dia in zip(puntos, dias):
            punto['dia'] = dia
            punto['hoy'] = dia == hoy
        ctx['grafica'] = {
            'puntos': puntos,
            'tope': tope,
            'ancho': self.ANCHO,
            'alto': self.ALTO,
            'linea': ' '.join(f"{p['x']},{p['y']}" for p in puntos),
            'area': (
                f"{puntos[0]['x']},{self.PISO} "
                + ' '.join(f"{p['x']},{p['y']}" for p in puntos)
                + f" {puntos[-1]['x']},{self.PISO}"
            ),
            'piso': self.PISO,
        }

        # --- Cartera de clientes -------------------------------------------
        clientes = Cliente.objects.filter(gym=gym, activo=True)
        total = clientes.count()
        # Una cancelada conserva fechas que abarcan hoy: sin excluirla, la
        # cartera se veria mas sana de lo que esta.
        vigentes_qs = ClienteMembresia.vigentes_en(hoy).filter(gym=gym)
        vigentes = vigentes_qs.values('cliente_id').distinct().count()
        por_vencer_total = (
            vigentes_qs.filter(fin__lte=en_una_semana)
            .values('cliente_id')
            .distinct()
            .count()
        )

        ctx['clientes_total'] = total
        ctx['membresias_vigentes'] = vigentes
        ctx['sin_membresia'] = total - vigentes
        ctx['por_vencer_total'] = por_vencer_total
        ctx['al_corriente'] = vigentes - por_vencer_total
        # Anchos de la barra apilada de salud de la cartera
        base = total or 1
        ctx['salud'] = {
            'al_corriente': round(ctx['al_corriente'] * 100 / base, 1),
            'por_vencer': round(por_vencer_total * 100 / base, 1),
            'sin_membresia': round(ctx['sin_membresia'] * 100 / base, 1),
            'cobertura': round(vigentes * 100 / base),
        }

        # Quien no aparece hace dos semanas: es a quien hay que llamar
        visitaron = (
            Asistencia.objects.filter(
                gym=gym, fecha_hora__date__gte=hoy - timezone.timedelta(days=14)
            )
            .values_list('cliente_id', flat=True)
            .distinct()
        )
        ausentes = clientes.exclude(pk__in=visitaron)
        ctx['ausentes'] = ausentes.count()
        ctx['ausentes_lista'] = ausentes[:4]

        # --- Lo mas vendido del mes -----------------------------------------
        inicio_mes = hoy.replace(day=1)
        ctx['top_productos'] = (
            VentaDetalle.objects.filter(
                venta__gym=gym,
                venta__estado=Venta.CONFIRMADA,
                venta__fecha__date__gte=inicio_mes,
                # Las lineas de membresia no son producto: agruparlas por
                # nombre las juntaria todas bajo una fila vacia.
                producto__isnull=False,
            )
            .values('producto__nombre')
            .annotate(piezas=Sum('cantidad'))
            .order_by('-piezas')[:5]
        )
        tope_top = max(
            [fila['piezas'] for fila in ctx['top_productos']] + [1]
        )
        for fila in ctx['top_productos']:
            fila['ancho'] = round(fila['piezas'] * 100 / tope_top)

        # --- Listas accionables --------------------------------------------
        ctx['por_vencer'] = (
            vigentes_qs.filter(fin__lte=en_una_semana)
            .select_related('cliente', 'membresia')
            .order_by('fin')[:4]
        )
        ctx['ultimos_accesos'] = (
            Asistencia.objects.filter(gym=gym, fecha_hora__date=hoy)
            .select_related('cliente')
            .order_by('-fecha_hora')[:5]
        )
        bajos = [
            inv
            for inv in InventarioSucursal.objects.filter(
                producto__gym=gym, producto__activo=True
            ).select_related('producto', 'sucursal')
            if inv.bajo_minimo
        ]
        ctx['stock_bajo_total'] = len(bajos)
        ctx['stock_bajo'] = bajos[:4]
        ctx['productos_total'] = Producto.objects.filter(gym=gym, activo=True).count()
        ctx['sucursales'] = Sucursal.objects.filter(gym=gym, activo=True)
        return ctx


# --- Panel SaaS (super administrador) ------------------------------------


class PlanListView(SuperUserRequiredMixin, ListView):
    model = Plan
    template_name = 'core/plan_list.html'
    context_object_name = 'planes'


class PlanCreateView(SuperUserRequiredMixin, CreateView):
    model = Plan
    form_class = PlanForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:plan_list')
    extra_context = {'titulo': 'Nuevo plan'}


class PlanUpdateView(SuperUserRequiredMixin, UpdateView):
    model = Plan
    form_class = PlanForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:plan_list')
    extra_context = {'titulo': 'Editar plan'}


class GymListView(SuperUserRequiredMixin, ListView):
    model = Gym
    template_name = 'core/gym_list.html'
    context_object_name = 'gyms'
    queryset = Gym.objects.select_related('plan')


class GymCreateView(SuperUserRequiredMixin, CreateView):
    model = Gym
    form_class = GymForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:gym_list')
    extra_context = {'titulo': 'Alta de gimnasio'}

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(
            self.request,
            f'Gimnasio "{self.object.nombre}" creado con su sucursal Principal. '
            'Ahora crea su usuario administrador.',
        )
        return respuesta


class GymUpdateView(SuperUserRequiredMixin, UpdateView):
    model = Gym
    form_class = GymForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:gym_list')
    extra_context = {'titulo': 'Editar gimnasio'}


# --- Sucursales del gym ---------------------------------------------------


class SucursalListView(GymRequiredMixin, ListView):
    model = Sucursal
    template_name = 'core/sucursal_list.html'
    context_object_name = 'sucursales'

    def get_queryset(self):
        return Sucursal.objects.filter(gym=self.gym).order_by('-activo', 'nombre')


class SucursalCreateView(AdminRequiredMixin, GymFormMixin, CreateView):
    model = Sucursal
    form_class = SucursalForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:sucursal_list')
    extra_context = {'titulo': 'Nueva sucursal'}

    def form_valid(self, form):
        if not self.gym.puede_crear_sucursal():
            messages.error(
                self.request,
                f'Tu plan {self.gym.plan.nombre} permite '
                f'{self.gym.plan.sucursales_max} sucursal(es).',
            )
            return redirect('core:sucursal_list')
        return super().form_valid(form)


class SucursalUpdateView(AdminRequiredMixin, GymFormMixin, UpdateView):
    model = Sucursal
    form_class = SucursalForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('core:sucursal_list')
    extra_context = {'titulo': 'Editar sucursal'}


class SucursalDeleteView(AdminRequiredMixin, SoftDeleteView):
    model = Sucursal
    success_url = reverse_lazy('core:sucursal_list')


# --- Configuracion del sitio publico --------------------------------------


class SitioUpdateView(AdminRequiredMixin, GymRequiredMixin, UpdateView):
    """Colores, frase, descripcion, portada y contacto de la pagina publica."""

    model = Gym
    form_class = GymSitioForm
    template_name = 'core/sitio.html'
    success_url = reverse_lazy('core:sitio')

    def get_object(self, queryset=None):
        return self.request.user.gym

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['paletas'] = PALETAS
        ctx['imagenes'] = self.gym.imagenes.filter(activo=True)
        ctx['imagen_form'] = GymImagenForm(gym=self.gym)
        ctx['menu'] = 'sitio'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Sitio actualizado.')
        return super().form_valid(form)


class SitioImagenCreateView(AdminRequiredMixin, GymRequiredMixin, View):
    """Subida de fotos a la galeria del sitio."""

    def post(self, request):
        form = GymImagenForm(request.POST, request.FILES, gym=request.user.gym)
        if form.is_valid():
            imagen = form.save(commit=False)
            imagen.gym = request.user.gym
            imagen.save()
            messages.success(request, 'Imagen agregada al sitio.')
        else:
            messages.error(request, f'No se pudo subir: {form.errors.as_text()}')
        return redirect('core:sitio')


class SitioImagenDeleteView(AdminRequiredMixin, GymRequiredMixin, View):
    def post(self, request, pk):
        imagen = get_object_or_404(GymImagen, pk=pk, gym=request.user.gym)
        imagen.soft_delete()
        messages.success(request, 'Imagen quitada del sitio.')
        return redirect('core:sitio')
