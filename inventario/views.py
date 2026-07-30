from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
    View,
)

from core.mixins import GymFormMixin, GymQuerysetMixin, GymRequiredMixin, SoftDeleteView
from inventario.forms import (
    CategoriaProductoForm,
    InventarioSucursalForm,
    MovimientoForm,
    ProductoAltaForm,
    ProductoForm,
)
from inventario.models import (
    CategoriaProducto,
    InventarioSucursal,
    Movimiento,
    Producto,
)


# --- Categorias -----------------------------------------------------------


class CategoriaListView(GymQuerysetMixin, ListView):
    model = CategoriaProducto
    template_name = 'inventario/categoria_list.html'
    context_object_name = 'categorias'


class CategoriaCreateView(GymFormMixin, CreateView):
    model = CategoriaProducto
    form_class = CategoriaProductoForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:categoria_list')
    extra_context = {'titulo': 'Nueva categoria'}


class CategoriaUpdateView(GymFormMixin, UpdateView):
    model = CategoriaProducto
    form_class = CategoriaProductoForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:categoria_list')
    extra_context = {'titulo': 'Editar categoria'}


class CategoriaDeleteView(SoftDeleteView):
    model = CategoriaProducto
    success_url = reverse_lazy('inventario:categoria_list')


# --- Productos ------------------------------------------------------------


class ProductoListView(GymQuerysetMixin, ListView):
    """
    El catalogo con sus existencias. Antes eran dos pantallas, y nadie quiere
    ver un producto sin saber cuantos le quedan.
    """

    model = Producto
    template_name = 'inventario/producto_list.html'
    context_object_name = 'productos'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().select_related('categoria')

    @property
    def sucursales(self):
        return self.gym.sucursales.filter(activo=True).order_by('nombre')

    @property
    def sucursal(self):
        """
        La que se esta viendo. El stock siempre es de una sucursal concreta.

        Una que no exista o sea de otro gimnasio cae a la propia, en vez de
        dejar la pantalla sin existencias.
        """
        pedida = self.request.GET.get('sucursal')
        if pedida:
            elegida = self.sucursales.filter(pk=pedida).first()
            if elegida is not None:
                return elegida
        return self.request.user.sucursal or self.sucursales.first()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sucursal = self.sucursal
        productos = ctx['productos']

        existencias = {
            inv.producto_id: inv
            for inv in InventarioSucursal.objects.filter(
                sucursal=sucursal, producto__in=productos
            )
        }
        for producto in productos:
            producto.inventario = existencias.get(producto.pk)

        ctx['sucursales'] = self.sucursales
        ctx['sucursal'] = sucursal
        return ctx


class ProductoCreateView(GymFormMixin, CreateView):
    """El alta carga tambien las existencias, dejando su movimiento de entrada."""

    model = Producto
    form_class = ProductoAltaForm
    template_name = 'inventario/producto_form.html'
    success_url = reverse_lazy('inventario:producto_list')
    extra_context = {'titulo': 'Nuevo producto'}

    def form_valid(self, form):
        cantidad = form.cleaned_data.get('cantidad') or 0
        with transaction.atomic():
            respuesta = super().form_valid(form)
            if cantidad:
                self.entrada = Movimiento.registrar(
                    producto=self.object,
                    sucursal=form.cleaned_data['sucursal'],
                    tipo=Movimiento.ENTRADA,
                    motivo=Movimiento.COMPRA,
                    cantidad=cantidad,
                    usuario=self.request.user,
                    nota='Existencias iniciales',
                )
        return respuesta

    def get_success_url(self):
        entrada = getattr(self, 'entrada', None)
        if entrada is not None:
            messages.success(
                self.request,
                f'Entraron {entrada.cantidad} piezas en {entrada.sucursal}.',
            )
        return super().get_success_url()


class ProductoUpdateView(GymFormMixin, UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'inventario/producto_form.html'
    success_url = reverse_lazy('inventario:producto_list')
    extra_context = {'titulo': 'Editar producto'}


class ProductoDeleteView(SoftDeleteView):
    model = Producto
    success_url = reverse_lazy('inventario:producto_list')


# --- Stock por sucursal ---------------------------------------------------
#
# La lista de existencias ya no vive aparte: sale junto al producto en
# ProductoListView. Aqui solo queda corregir un conteo.


class InventarioUpdateView(GymRequiredMixin, UpdateView):
    model = InventarioSucursal
    form_class = InventarioSucursalForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:producto_list')
    extra_context = {'titulo': 'Ajustar existencias'}

    def get_queryset(self):
        return InventarioSucursal.objects.filter(producto__gym=self.gym)


# --- Movimientos ----------------------------------------------------------


class MovimientoListView(GymQuerysetMixin, ListView):
    """El libro: todo lo que entro y salio, y por que."""

    model = Movimiento
    template_name = 'inventario/movimiento_list.html'
    context_object_name = 'movimientos'
    paginate_by = 50
    solo_activos = False  # un movimiento no se da de baja, se corrige con otro

    def get_queryset(self):
        qs = super().get_queryset().select_related('producto', 'sucursal', 'usuario')
        motivo = self.request.GET.get('motivo')
        if motivo:
            qs = qs.filter(motivo=motivo)
        producto = self.request.GET.get('producto')
        if producto:
            qs = qs.filter(producto_id=producto)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['motivos'] = Movimiento.MOTIVOS
        ctx['motivo'] = self.request.GET.get('motivo', '')
        ctx['productos'] = Producto.objects.filter(gym=self.gym, activo=True)
        ctx['producto_id'] = self.request.GET.get('producto', '')
        ctx['menu'] = 'inventario'
        return ctx


class MovimientoCreateView(GymRequiredMixin, FormView):
    """
    Registrar a mano lo que entra o sale. Las ventas no pasan por aqui: las
    anota el punto de venta al cobrar.
    """

    form_class = MovimientoForm
    template_name = 'inventario/movimiento_form.html'
    success_url = reverse_lazy('inventario:movimiento_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.gym
        kwargs['inicial_producto'] = self.request.GET.get('producto')
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Nuevo movimiento'
        ctx['menu'] = 'inventario'
        return ctx

    def form_valid(self, form):
        datos = form.cleaned_data
        producto = datos['producto']
        costo_anterior = producto.precio_compra

        movimiento = Movimiento.registrar(
            producto=producto,
            sucursal=datos['sucursal'],
            tipo=datos['tipo'],
            motivo=datos['motivo'],
            cantidad=datos['cantidad'],
            precio=datos.get('precio'),
            usuario=self.request.user,
            nota=datos.get('nota', ''),
        )

        verbo = 'Entraron' if movimiento.tipo == Movimiento.ENTRADA else 'Salieron'
        aviso = (
            f'{verbo} {movimiento.cantidad} de {producto.nombre}. Quedan '
            f'{producto.stock_en(movimiento.sucursal)} en {movimiento.sucursal}.'
        )
        if producto.precio_compra != costo_anterior:
            aviso += (
                f' El costo pasa de {costo_anterior} a {producto.precio_compra}, '
                'que es con el que se calcula la ganancia.'
            )
        messages.success(self.request, aviso)
        return super().form_valid(form)
