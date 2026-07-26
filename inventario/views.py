from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from core.mixins import GymFormMixin, GymQuerysetMixin, GymRequiredMixin, SoftDeleteView
from inventario.forms import (
    CategoriaProductoForm,
    CompraDetalleForm,
    CompraForm,
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
    model = Producto
    template_name = 'inventario/producto_list.html'
    context_object_name = 'productos'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().select_related('categoria')


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
                self.compra = self._comprar(
                    producto=self.object,
                    cantidad=cantidad,
                    sucursal=form.cleaned_data['sucursal'],
                    proveedor=form.cleaned_data.get('proveedor'),
                )
        return respuesta

    def _comprar(self, producto, cantidad, sucursal, proveedor):
        """Deja la entrada asentada como compra confirmada, que es la que mueve stock."""
        compra = Compra.objects.create(
            gym=self.gym,
            sucursal=sucursal,
            proveedor=proveedor,
            usuario=self.request.user,
        )
        CompraDetalle.objects.create(
            compra=compra,
            producto=producto,
            cantidad=cantidad,
            precio=producto.precio_compra,
        )
        compra.confirmar()
        return compra

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


class InventarioListView(GymRequiredMixin, ListView):
    model = InventarioSucursal
    template_name = 'inventario/inventario_list.html'
    context_object_name = 'inventarios'

    def get_queryset(self):
        qs = InventarioSucursal.objects.filter(
            producto__gym=self.gym, producto__activo=True
        ).select_related('producto', 'sucursal')
        sucursal_id = self.request.GET.get('sucursal')
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sucursales'] = self.gym.sucursales.filter(activo=True)
        ctx['sucursal_id'] = self.request.GET.get('sucursal', '')
        return ctx


class InventarioUpdateView(GymRequiredMixin, UpdateView):
    model = InventarioSucursal
    form_class = InventarioSucursalForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('inventario:inventario_list')
    extra_context = {'titulo': 'Ajustar inventario'}

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
