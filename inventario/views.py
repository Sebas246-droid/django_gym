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
    CompraDetalleForm,
    CompraForm,
    EntradaForm,
    InventarioSucursalForm,
    ProductoAltaForm,
    ProductoForm,
    ProveedorForm,
)
from inventario.models import (
    CategoriaProducto,
    Compra,
    CompraDetalle,
    InventarioSucursal,
    Producto,
    Proveedor,
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


class EntradaProductoView(GymRequiredMixin, FormView):
    """
    Llego mas de algo que ya vendes. Pide cantidad y costo, y deja la compra
    asentada: asi el stock sube con rastro del dinero, en un solo paso.
    """

    form_class = EntradaForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:producto_list')

    @property
    def producto(self):
        return get_object_or_404(
            Producto, pk=self.kwargs['pk'], gym=self.gym, activo=True
        )

    def get_form_kwargs(self):
        # No es un ModelForm: el gym se pasa a mano, sin GymFormMixin.
        kwargs = super().get_form_kwargs()
        kwargs['gym'] = self.gym
        kwargs['producto'] = self.producto
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = f'Entrada de {self.producto.nombre}'
        return ctx

    def form_valid(self, form):
        compra = Compra.registrar_entrada(
            producto=self.producto,
            sucursal=form.cleaned_data['sucursal'],
            cantidad=form.cleaned_data['cantidad'],
            precio=form.cleaned_data.get('precio'),
            proveedor=form.cleaned_data.get('proveedor'),
            usuario=self.request.user,
        )
        messages.success(
            self.request,
            f'Entraron {form.cleaned_data["cantidad"]} de '
            f'{self.producto.nombre}. Quedan '
            f'{self.producto.stock_en(compra.sucursal)} en {compra.sucursal}.',
        )
        return super().form_valid(form)


class ProductoCreateView(GymFormMixin, CreateView):
    """El alta carga tambien las existencias, levantando la compra que las respalda."""

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
                self.compra = Compra.registrar_entrada(
                    producto=self.object,
                    sucursal=form.cleaned_data['sucursal'],
                    cantidad=cantidad,
                    proveedor=form.cleaned_data.get('proveedor'),
                    usuario=self.request.user,
                )
        return respuesta

    def get_success_url(self):
        compra = getattr(self, 'compra', None)
        if compra is None:
            return super().get_success_url()
        messages.success(
            self.request,
            f'Se registro la compra #{compra.pk} con {compra.detalles.first().cantidad} '
            f'piezas en {compra.sucursal}.',
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


# --- Proveedores ----------------------------------------------------------


class ProveedorListView(GymQuerysetMixin, ListView):
    model = Proveedor
    template_name = 'inventario/proveedor_list.html'
    context_object_name = 'proveedores'


class ProveedorCreateView(GymFormMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:proveedor_list')
    extra_context = {'titulo': 'Nuevo proveedor'}


class ProveedorUpdateView(GymFormMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:proveedor_list')
    extra_context = {'titulo': 'Editar proveedor'}


class ProveedorDeleteView(SoftDeleteView):
    model = Proveedor
    success_url = reverse_lazy('inventario:proveedor_list')


# --- Compras --------------------------------------------------------------


class CompraListView(GymQuerysetMixin, ListView):
    model = Compra
    template_name = 'inventario/compra_list.html'
    context_object_name = 'compras'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().select_related('proveedor', 'sucursal', 'usuario')


class CompraCreateView(GymFormMixin, CreateView):
    model = Compra
    form_class = CompraForm
    template_name = 'core/form.html'
    extra_context = {'titulo': 'Nueva compra'}

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('inventario:compra_detail', args=[self.object.pk])


class CompraDetailView(GymQuerysetMixin, DetailView):
    model = Compra
    template_name = 'inventario/compra_detail.html'
    context_object_name = 'compra'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['detalles'] = self.object.detalles.select_related('producto')
        ctx['form'] = CompraDetalleForm(gym=self.gym)
        return ctx


class CompraDetalleCreateView(GymRequiredMixin, View):
    def post(self, request, pk):
        compra = get_object_or_404(Compra, pk=pk, gym=request.user.gym)
        if compra.estado == Compra.CONFIRMADA:
            messages.error(request, 'La compra ya esta confirmada.')
            return redirect('inventario:compra_detail', pk=pk)

        form = CompraDetalleForm(request.POST, gym=request.user.gym)
        if form.is_valid():
            detalle = form.save(commit=False)
            detalle.compra = compra
            detalle.precio = form.cleaned_data['precio']
            detalle.save()
            compra.recalcular_total()
            messages.success(request, 'Producto agregado a la compra.')
        else:
            messages.error(request, f'Revisa los datos: {form.errors.as_text()}')
        return redirect('inventario:compra_detail', pk=pk)


class CompraDetalleDeleteView(GymRequiredMixin, View):
    def post(self, request, pk, detalle_pk):
        compra = get_object_or_404(Compra, pk=pk, gym=request.user.gym)
        if compra.estado == Compra.CONFIRMADA:
            messages.error(request, 'La compra ya esta confirmada.')
            return redirect('inventario:compra_detail', pk=pk)
        CompraDetalle.objects.filter(pk=detalle_pk, compra=compra).delete()
        compra.recalcular_total()
        messages.success(request, 'Producto eliminado de la compra.')
        return redirect('inventario:compra_detail', pk=pk)


class CompraConfirmarView(GymRequiredMixin, View):
    """Confirmar compra => InventarioSucursal + cantidad."""

    def post(self, request, pk):
        compra = get_object_or_404(Compra, pk=pk, gym=request.user.gym)
        if not compra.detalles.exists():
            messages.error(request, 'La compra no tiene productos.')
        else:
            with transaction.atomic():
                aplicada = compra.confirmar()
            if aplicada:
                messages.success(request, 'Compra confirmada. Inventario actualizado.')
            else:
                messages.info(request, 'La compra ya estaba confirmada.')
        return redirect('inventario:compra_detail', pk=pk)
