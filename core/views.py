from django.contrib import messages
from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.forms import PALETAS, GymForm, GymImagenForm, GymSitioForm, PlanForm, SucursalForm
from core.mixins import (
    AdminRequiredMixin,
    GymFormMixin,
    GymRequiredMixin,
    SoftDeleteView,
    SuperUserRequiredMixin,
)
from core.models import Gym, GymImagen, Plan, Sucursal
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
        ctx['membresias'] = Membresia.objects.filter(
            gym=gym, activo=True, visible_en_sitio=True
        ).order_by('precio', 'nombre')
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
    Es la primera pantalla que ve el dueno del gimnasio cada manana.

    Va ordenada como se cobra, no como se ve bonito: primero a quien hay que
    renovarle en los proximos dias (que es lo unico de aqui que todavia se
    puede salvar con una llamada), luego a quien ya se le vencio, despues las
    cifras del dia y al final la actividad.
    """

    template_name = 'core/dashboard.html'
    extra_context = {'menu': 'dashboard'}

    #: Cuantos renglones se ensenan de cada lista antes de mandar a la
    #: pantalla completa. Mas de esto y el tablero deja de ser un resumen.
    FILAS = 8

    @cached_property
    def sucursal_vista(self):
        """
        De que sede son las cifras. None es el gimnasio completo.

        Abre en "todas" a proposito: el tablero lo mira sobre todo el dueno, y
        cambiarle el default a la sede del usuario le escondería la mitad del
        negocio sin avisar. Quien lleva una sola sucursal la elige y el sistema
        no vuelve a preguntar mientras no cambie la url.
        """
        pedida = self.request.GET.get('sucursal', '')
        if pedida.isdigit():
            return self.sucursales.filter(pk=pedida).first()
        return None

    def _de_la_sede(self, qs, campo='sucursal'):
        """Acota una consulta a la sede elegida. Sin sede, la deja como esta."""
        if self.sucursal_vista is None:
            return qs
        return qs.filter(**{campo: self.sucursal_vista})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        gym = self.request.user.gym
        hoy = timezone.localdate()
        sede = self.sucursal_vista
        dias = [hoy - timezone.timedelta(days=atras) for atras in range(6, -1, -1)]

        ctx['sucursales'] = self.sucursales
        ctx['sucursal_vista'] = sede
        # Con una sola sucursal el selector no aporta nada y estorba.
        ctx['varias_sucursales'] = self.sucursales.count() > 1
        ctx['dias_aviso'] = ClienteMembresia.DIAS_AVISO

        # --- La cartera, de donde salen las dos listas ----------------------
        # Se corta por la sede del socio, no por donde compro: es "cuanta de MI
        # gente esta al corriente", y alguien de Centro que renovo de paso en
        # Norte sigue siendo cartera de Centro.
        clientes = self._de_la_sede(Cliente.objects.filter(gym=gym, activo=True))
        total = clientes.count()

        # Una cancelada conserva fechas que abarcan hoy: sin excluirla, la
        # cartera se veria mas sana de lo que esta.
        vigentes_qs = self._de_la_sede(
            ClienteMembresia.vigentes_en(hoy).filter(gym=gym), 'cliente__sucursal'
        )
        vigentes = vigentes_qs.values('cliente_id').distinct().count()

        # --- 1) Por vencer --------------------------------------------------
        por_vencer_qs = vigentes_qs.filter(
            fin__lte=hoy + timezone.timedelta(days=ClienteMembresia.DIAS_AVISO)
        )
        ctx['por_vencer_total'] = por_vencer_qs.values('cliente_id').distinct().count()
        ctx['por_vencer'] = list(
            por_vencer_qs.select_related('cliente', 'membresia').order_by('fin')[
                : self.FILAS
            ]
        )
        for cm in ctx['por_vencer']:
            cm.dias = (cm.fin - hoy).days

        # --- 2) Vencidas ----------------------------------------------------
        # La ultima membresia de quien hoy no tiene ninguna que le alcance.
        # Estar cubierto NO se corta por sede: si renovo de paso en otra
        # sucursal sigue al corriente, y sacarlo aqui seria hablarle para
        # cobrarle algo que ya pago.
        cubiertos = (
            ClienteMembresia.objects.filter(gym=gym, activo=True, fin__gte=hoy)
            .exclude(estado=ClienteMembresia.CANCELADA)
            .values('cliente_id')
        )
        vencidos_qs = (
            clientes.exclude(pk__in=cubiertos)
            .annotate(
                vencio=Max(
                    'membresias__fin',
                    filter=Q(membresias__activo=True)
                    & ~Q(membresias__estado=ClienteMembresia.CANCELADA),
                )
            )
            # Sin fecha es que nunca compro: ese no esta vencido, esta sin
            # estrenar, y sale en su propio KPI.
            .filter(vencio__isnull=False)
            .order_by('-vencio')
        )
        ctx['vencidos_total'] = vencidos_qs.count()
        ctx['vencidos'] = list(vencidos_qs[: self.FILAS])
        for cliente in ctx['vencidos']:
            cliente.dias_vencida = (hoy - cliente.vencio).days

        # --- 3) Los KPIs ----------------------------------------------------
        # El desglose del dinero es por donde se cobro, no por que se vendio:
        # una membresia cobrada en caja ya viene dentro del total de esa venta.
        ventas_hoy = self._de_la_sede(
            Venta.objects.filter(gym=gym, fecha__date=hoy, estado=Venta.CONFIRMADA)
        )
        ingreso_mostrador = ventas_hoy.aggregate(t=Sum('total'))['t'] or 0
        ingreso_membresias = sum(
            cm.total for cm in ClienteMembresia.cobradas_aparte(gym, hoy, sede)
        )
        ctx['ingreso_mostrador'] = ingreso_mostrador
        ctx['ingreso_membresias'] = ingreso_membresias
        ctx['ingresos_hoy'] = ingreso_mostrador + ingreso_membresias
        ctx['ventas_hoy'] = ventas_hoy.count()
        # Aqui si cuentan todas: es cuantas se vendieron, no cuanto entro.
        ctx['membresias_vendidas_hoy'] = self._de_la_sede(
            ClienteMembresia.objects.filter(
                gym=gym, activo=True, fecha_pago__date=hoy
            ).exclude(estado='cancelada')
        ).count()

        # Los productos de la semana se suman de un golpe; las membresias van
        # dia por dia porque hay que dejar fuera las que ya vienen dentro de
        # una venta, o el ingreso se contaria dos veces.
        productos_semana = (
            self._de_la_sede(
                Venta.objects.filter(
                    gym=gym, fecha__date__gte=dias[0], estado=Venta.CONFIRMADA
                )
            ).aggregate(t=Sum('total'))['t']
            or 0
        )
        ingreso_semana = productos_semana + sum(
            cm.total
            for dia in dias
            for cm in ClienteMembresia.cobradas_aparte(gym, dia, sede)
        )
        ctx['ingreso_semana'] = ingreso_semana
        ctx['ingreso_dia_promedio'] = round(ingreso_semana / len(dias))

        ctx['clientes_total'] = total
        ctx['membresias_vigentes'] = vigentes
        ctx['sin_membresia'] = total - vigentes
        ctx['cobertura'] = round(vigentes * 100 / (total or 1))

        # --- 4) Entradas ----------------------------------------------------
        entradas = self._de_la_sede(
            Asistencia.objects.filter(gym=gym, tipo=Asistencia.ENTRADA)
        )
        conteos = [entradas.filter(fecha_hora__date=dia).count() for dia in dias]
        techo = max(conteos + [1])
        ctx['entradas_semana'] = [
            {
                'dia': dia,
                'valor': valor,
                # Un dia en cero tambien se dibuja: la barra minima se lee como
                # "no vino nadie", no como "falta el dato".
                'alto': max(round(valor * 100 / techo), 4),
                'hoy': dia == hoy,
            }
            for dia, valor in zip(dias, conteos)
        ]
        ctx['asistencias_hoy'] = conteos[-1]
        ctx['variacion_entradas'] = conteos[-1] - conteos[-2]

        # Quien sigue dentro: su ultimo movimiento de hoy fue una entrada
        movimientos = self._de_la_sede(
            Asistencia.objects.filter(gym=gym, fecha_hora__date=hoy)
        ).order_by('fecha_hora')
        ultimo_por_cliente = {}
        for mov in movimientos:
            ultimo_por_cliente[mov.cliente_id] = mov.tipo
        ctx['dentro_ahora'] = sum(
            1 for tipo in ultimo_por_cliente.values() if tipo == Asistencia.ENTRADA
        )

        # --- Lo mas vendido del mes -----------------------------------------
        inicio_mes = hoy.replace(day=1)
        ctx['top_productos'] = (
            self._de_la_sede(
                VentaDetalle.objects.filter(
                    venta__gym=gym,
                    venta__estado=Venta.CONFIRMADA,
                    venta__fecha__date__gte=inicio_mes,
                    # Las lineas de membresia no son producto: agruparlas por
                    # nombre las juntaria todas bajo una fila vacia.
                    producto__isnull=False,
                ),
                'venta__sucursal',
            )
            .values('producto__nombre')
            .annotate(piezas=Sum('cantidad'))
            .order_by('-piezas')[:5]
        )
        tope_top = max([fila['piezas'] for fila in ctx['top_productos']] + [1])
        for fila in ctx['top_productos']:
            fila['ancho'] = round(fila['piezas'] * 100 / tope_top)
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
    """
    Baja de una sede. No se permite si queda gente asignada a ella.

    Antes se daba de baja sin mirar: quien seguia asignado se quedaba cobrando
    en una sucursal que el resto del sistema ya daba por cerrada, y el
    inventario le ofrecia otra distinta. Es mas barato obligar a mover a la
    gente primero que perseguir despues las ventas que quedaron en el limbo.
    """

    model = Sucursal
    success_url = reverse_lazy('core:sucursal_list')

    def form_valid(self, form):
        sucursal = self.get_object()

        if self.gym.sucursales.filter(activo=True).count() < 2:
            messages.error(
                self.request,
                'Es la unica sucursal activa: el gimnasio no puede quedarse sin ninguna.',
            )
            return redirect(self.success_url)

        asignados = sucursal.users.filter(is_active=True)
        if asignados.exists():
            nombres = ', '.join(str(u) for u in asignados[:3])
            resto = asignados.count() - 3
            if resto > 0:
                nombres += f' y {resto} mas'
            messages.error(
                self.request,
                f'No se puede dar de baja {sucursal}: siguen asignados {nombres}. '
                'Muevelos a otra sucursal primero.',
            )
            return redirect(self.success_url)

        return super().form_valid(form)


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
        ctx['membresias'] = Membresia.objects.filter(
            gym=self.gym, activo=True
        ).order_by('precio', 'nombre')
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


class SitioMembresiasView(AdminRequiredMixin, GymRequiredMixin, View):
    """
    Elige que membresias del catalogo se publican como precios en la pagina.

    Llega la lista completa de marcadas: lo que no viene en el POST se apaga.
    Asi una casilla que se desmarca se guarda igual que una que se marca, sin
    tener que mandar el estado anterior.
    """

    def post(self, request):
        del_gym = Membresia.objects.filter(gym=request.user.gym, activo=True)
        marcadas = {int(pk) for pk in request.POST.getlist('visibles') if pk.isdigit()}

        del_gym.filter(pk__in=marcadas).update(visible_en_sitio=True)
        del_gym.exclude(pk__in=marcadas).update(visible_en_sitio=False)

        messages.success(request, 'Membresias del sitio actualizadas.')
        return redirect('core:sitio')
