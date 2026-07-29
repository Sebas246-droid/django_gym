from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from clientes.forms import ClienteForm, ClienteMembresiaForm, MembresiaForm
from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.mixins import GymFormMixin, GymQuerysetMixin, GymRequiredMixin, SoftDeleteView
from entrenamiento.models import Entrenamiento


# --- Clientes -------------------------------------------------------------


class ClienteListView(GymQuerysetMixin, ListView):
    model = Cliente
    template_name = 'clientes/cliente_list.html'
    context_object_name = 'clientes'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related('sucursal')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(telefono__icontains=q)
                | Q(correo__icontains=q)
                | Q(numero_usuario__startswith=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ClienteDetailView(GymQuerysetMixin, DetailView):
    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['membresias'] = self.object.membresias.select_related(
            'membresia', 'usuario'
        )
        ctx['asistencias'] = self.object.asistencias.select_related('entrenamiento')[:20]
        # El historico esta ordenado del mas reciente al mas viejo.
        ctx['ultimo_peso'] = self.object.medidas.first()
        return ctx


class ClienteCreateView(GymFormMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('clientes:cliente_list')
    extra_context = {'titulo': 'Nuevo cliente'}

    def form_valid(self, form):
        if not self.gym.puede_crear_cliente():
            messages.error(
                self.request,
                f'Tu plan {self.gym.plan.nombre} permite '
                f'{self.gym.plan.clientes_max} clientes.',
            )
            return redirect('clientes:cliente_list')
        return super().form_valid(form)


class ClienteUpdateView(GymFormMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('clientes:cliente_list')
    extra_context = {'titulo': 'Editar cliente'}


class ClienteDeleteView(SoftDeleteView):
    model = Cliente
    success_url = reverse_lazy('clientes:cliente_list')


class ClienteCredencialView(GymQuerysetMixin, DetailView):
    """
    Credencial del socio, sola en la pagina y a tamano de tarjeta. Se imprime o
    se guarda como PDF desde el navegador: no hace falta generar el archivo en
    el servidor ni sumar una libreria para eso.
    """

    model = Cliente
    template_name = 'clientes/credencial.html'
    context_object_name = 'cliente'


# --- Membresias (catalogo) ------------------------------------------------


class MembresiaListView(GymQuerysetMixin, ListView):
    model = Membresia
    template_name = 'clientes/membresia_list.html'
    context_object_name = 'membresias'


class MembresiaCreateView(GymFormMixin, CreateView):
    model = Membresia
    form_class = MembresiaForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('clientes:membresia_list')
    extra_context = {'titulo': 'Nueva membresia'}


class MembresiaUpdateView(GymFormMixin, UpdateView):
    model = Membresia
    form_class = MembresiaForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('clientes:membresia_list')
    extra_context = {'titulo': 'Editar membresia'}


class MembresiaDeleteView(SoftDeleteView):
    model = Membresia
    success_url = reverse_lazy('clientes:membresia_list')


# --- Venta de membresia ---------------------------------------------------


class ClienteMembresiaListView(GymQuerysetMixin, ListView):
    model = ClienteMembresia
    template_name = 'clientes/clientemembresia_list.html'
    context_object_name = 'ventas_membresia'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().select_related('cliente', 'membresia', 'usuario')


class ClienteMembresiaCreateView(GymFormMixin, CreateView):
    model = ClienteMembresia
    form_class = ClienteMembresiaForm
    template_name = 'clientes/clientemembresia_form.html'
    success_url = reverse_lazy('clientes:clientemembresia_list')
    extra_context = {'titulo': 'Vender membresia'}
    mensaje_exito = None  # este flujo da su propio aviso, con las fechas

    def get_initial(self):
        inicial = super().get_initial()
        inicial['inicio'] = timezone.localdate()
        cliente_id = self.request.GET.get('cliente')
        if not cliente_id:
            return inicial

        inicial['cliente'] = cliente_id
        cliente = Cliente.objects.filter(
            pk=cliente_id, gym=self.gym, activo=True
        ).first()
        if cliente is not None:
            # Renovando, la fecha que se propone es la que no le quita dias.
            inicial['inicio'] = cliente.inicio_siguiente_membresia
        return inicial

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        respuesta = super().form_valid(form)

        anterior = getattr(form, 'encadenada_tras', None)
        if anterior is None:
            messages.success(self.request, 'Membresia registrada y cobro guardado.')
        else:
            messages.success(
                self.request,
                f'Cobro guardado. Como la anterior corre hasta el '
                f'{anterior.fin.strftime("%d/%m/%Y")}, esta arranca el '
                f'{self.object.inicio.strftime("%d/%m/%Y")} y vence el '
                f'{self.object.fin.strftime("%d/%m/%Y")}.',
            )
        return respuesta


class ClienteMembresiaUpdateView(GymFormMixin, UpdateView):
    """Corregir un cobro mal capturado: precio, fechas o metodo de pago."""

    model = ClienteMembresia
    form_class = ClienteMembresiaForm
    template_name = 'clientes/clientemembresia_form.html'
    success_url = reverse_lazy('clientes:clientemembresia_list')
    extra_context = {'titulo': 'Editar venta de membresia'}
    mensaje_exito = 'Venta de membresia corregida.'

    def get_queryset(self):
        # Una cancelada ya no se edita: primero habria que reactivarla.
        return super().get_queryset().exclude(estado='cancelada')


class ClienteMembresiaCancelarView(GymRequiredMixin, View):
    """
    Cancela el cobro sin borrarlo: el historial del socio y el corte de caja
    tienen que seguir mostrando que existio y que se deshizo.
    """

    def post(self, request, pk):
        venta = get_object_or_404(
            ClienteMembresia, pk=pk, gym=self.gym, activo=True
        )
        if venta.estado == 'cancelada':
            messages.info(request, 'Esa venta ya estaba cancelada.')
        else:
            venta.estado = 'cancelada'
            venta.save(update_fields=['estado', 'updated_at'])
            messages.success(
                request, f'Se cancelo la membresia de {venta.cliente.nombre}.'
            )
        return redirect(self._volver(request))

    def _volver(self, request):
        """
        La pantalla de origen viaja en el POST, asi que hay que comprobar que
        apunte a este sitio: si no, cualquiera podria usarla para mandar a un
        usuario con sesion a una pagina de fuera.
        """
        destino = request.POST.get('volver')
        if destino and url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return destino
        return 'clientes:clientemembresia_list'


# --- Asistencias ----------------------------------------------------------


class AsistenciaListView(GymQuerysetMixin, ListView):
    model = Asistencia
    template_name = 'clientes/asistencia_list.html'
    context_object_name = 'asistencias'
    paginate_by = 30
    solo_activos = False

    def get_queryset(self):
        return super().get_queryset().select_related(
            'cliente', 'sucursal', 'entrenamiento', 'usuario'
        )


class CheckinView(GymRequiredMixin, TemplateView):
    """
    Kiosco de acceso: pantalla unica para una tablet fija en la entrada.
    El cliente teclea su numero y obtiene el veredicto; nada mas.
    """

    template_name = 'clientes/kiosco.html'
    extra_context = {'menu': 'checkin'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # El resultado del acceso viaja por sesion para que recargar no repita
        # el registro (patron POST-Redirect-GET).
        ctx['resultado'] = self.request.session.pop('acceso', None)

        # Tantas casillas como digitos usa la numeracion del gimnasio.
        digitos = max(
            (len(n) for n in Cliente.objects.filter(gym=self.gym, activo=True)
             .values_list('numero_usuario', flat=True) if n),
            default=4,
        )
        ctx['digitos'] = digitos
        ctx['digitos_rango'] = range(digitos)

        # Segundo paso: solo se ofrece a quien acaba de pasar y aun no eligio.
        resultado = ctx['resultado'] or {}
        if resultado.get('asistencia_id') and resultado.get('estado') in ('ok', 'aviso'):
            ctx['entrenamientos'] = Entrenamiento.objects.filter(
                gym=self.gym, activo=True
            )
        # Con segundo paso la pantalla espera mas antes de volver al teclado.
        ctx['segundos'] = 16 if ctx.get('entrenamientos') else 7

        # Unica pantalla auxiliar: buscar el numero para quien no lo recuerda.
        ctx['buscando'] = 'buscar' in self.request.GET
        q = self.request.GET.get('q', '').strip()
        ctx['q'] = q
        if q:
            ctx['coincidencias'] = Cliente.objects.filter(
                gym=self.gym, activo=True
            ).filter(
                Q(nombre__icontains=q) | Q(telefono__icontains=q)
                | Q(numero_usuario__startswith=q)
            )[:8]
        return ctx

    def post(self, request, *args, **kwargs):
        numero = request.POST.get('numero_usuario', '').strip()
        tipo = request.POST.get('tipo', Asistencia.ENTRADA)
        entrenamiento_id = request.POST.get('entrenamiento') or None

        request.session['acceso'] = self._resolver(numero, tipo, entrenamiento_id)
        return redirect('clientes:checkin')

    # --- Logica del acceso ------------------------------------------------

    @staticmethod
    def _fecha(valor):
        return valor.strftime('%d/%m/%Y')

    @staticmethod
    def _dias(cantidad):
        return '1 dia' if cantidad == 1 else f'{cantidad} dias'

    def _resolver(self, numero, tipo, entrenamiento_id):
        if not numero.isdigit():
            return {
                'estado': 'invalido',
                'titulo': 'Numero invalido',
                'mensaje': 'Teclea solo digitos, por ejemplo 1000.',
            }

        cliente = Cliente.objects.filter(
            gym=self.gym, numero_usuario=numero, activo=True
        ).first()
        if not cliente:
            return {
                'estado': 'invalido',
                'titulo': 'No encontrado',
                'mensaje': f'Ningun cliente activo tiene el numero {numero}.',
                'numero': numero,
            }

        asistencia = self._registrar(cliente, tipo, entrenamiento_id)
        vigente = cliente.membresia_vigente
        base = {
            'cliente_id': cliente.pk,
            'asistencia_id': asistencia.pk,
            'nombre': cliente.nombre,
            'numero': cliente.numero_usuario,
            'foto': cliente.foto.url if cliente.foto else '',
            'inicial': cliente.nombre[:1].upper(),
            'tipo': asistencia.get_tipo_display(),
            'hora': timezone.localtime(asistencia.fecha_hora).strftime('%H:%M'),
        }

        if vigente:
            dias = cliente.dias_restantes
            estado = 'ok' if dias > 3 else 'aviso'
            return base | {
                'estado': estado,
                'titulo': 'Adelante' if estado == 'ok' else 'Pasa, pero renueva',
                'mensaje': (
                    f'{vigente.membresia.nombre} vigente hasta el '
                    f'{self._fecha(vigente.fin)}.'
                ),
                'detalle': (
                    f'Te quedan {self._dias(dias)}.'
                    if estado == 'ok'
                    else f'Solo te quedan {self._dias(dias)}: pasa a renovar.'
                ),
            }

        ultima = cliente.ultima_membresia
        if ultima:
            mensaje = (
                f'Tu membresia {ultima.membresia.nombre} vencio el '
                f'{self._fecha(ultima.fin)}.'
            )
        else:
            mensaje = 'Todavia no tienes una membresia registrada.'
        return base | {
            'estado': 'vencida',
            'titulo': 'Membresia vencida',
            'mensaje': mensaje,
            'detalle': 'Pasa a recepcion para renovar.',
        }

    def _registrar(self, cliente, tipo, entrenamiento_id):
        entrenamiento = None
        if entrenamiento_id:
            entrenamiento = Entrenamiento.objects.filter(
                pk=entrenamiento_id, gym=self.gym
            ).first()
        if tipo not in dict(Asistencia.TIPOS):
            tipo = Asistencia.ENTRADA
        return Asistencia.objects.create(
            gym=self.gym,
            sucursal=self.request.user.sucursal or cliente.sucursal,
            cliente=cliente,
            usuario=self.request.user,
            entrenamiento=entrenamiento,
            tipo=tipo,
        )


class AsistenciaEntrenamientoView(GymRequiredMixin, View):
    """
    Segundo paso del kiosco: ya adentro, la persona elige que va a entrenar.
    Se aplica sobre la asistencia que se acaba de registrar.
    """

    def post(self, request, pk):
        asistencia = get_object_or_404(Asistencia, pk=pk, gym=request.user.gym)
        entrenamiento = Entrenamiento.objects.filter(
            pk=request.POST.get('entrenamiento'), gym=request.user.gym, activo=True
        ).first()

        if entrenamiento:
            asistencia.entrenamiento = entrenamiento
            asistencia.save(update_fields=['entrenamiento', 'updated_at'])
            cliente = asistencia.cliente
            request.session['acceso'] = {
                'estado': 'ok',
                'titulo': 'Listo',
                'nombre': cliente.nombre,
                'numero': cliente.numero_usuario,
                'foto': cliente.foto.url if cliente.foto else '',
                'inicial': cliente.nombre[:1].upper(),
                'mensaje': f'Hoy toca {entrenamiento.nombre}.',
                'detalle': 'Que tengas buen entrenamiento.',
            }
        return redirect('clientes:checkin')


class AsistenciaRegistrarView(GymRequiredMixin, View):
    """Registro directo desde la ficha del cliente o desde la busqueda."""

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk, gym=request.user.gym, activo=True)
        vista = CheckinView()
        vista.request = request
        request.session['acceso'] = vista._resolver(
            cliente.numero_usuario,
            request.POST.get('tipo', Asistencia.ENTRADA),
            request.POST.get('entrenamiento') or None,
        )
        return redirect('clientes:checkin')
