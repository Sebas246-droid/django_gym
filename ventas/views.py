from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from core.mixins import GymFormMixin, GymQuerysetMixin, GymRequiredMixin
from ventas.forms import VentaDetalleForm, VentaForm
from ventas.models import Venta, VentaDetalle


class VentaListView(GymQuerysetMixin, ListView):
    model = Venta
    template_name = 'ventas/venta_list.html'
    context_object_name = 'ventas'
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().select_related('cliente', 'sucursal', 'usuario')


class VentaCreateView(GymFormMixin, CreateView):
    model = Venta
    form_class = VentaForm
    template_name = 'core/form.html'
    extra_context = {'titulo': 'Nueva venta'}

    def get_initial(self):
        inicial = super().get_initial()
        if self.request.user.sucursal_id:
            inicial['sucursal'] = self.request.user.sucursal_id
        return inicial

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('ventas:venta_detail', args=[self.object.pk])


class VentaDetailView(GymQuerysetMixin, DetailView):
    model = Venta
    template_name = 'ventas/venta_detail.html'
    context_object_name = 'venta'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['detalles'] = self.object.detalles.select_related('producto')
        ctx['form'] = VentaDetalleForm(gym=self.gym)
        return ctx


class VentaDetalleCreateView(GymRequiredMixin, View):
    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, gym=request.user.gym)
        if venta.estado == Venta.CONFIRMADA:
            messages.error(request, 'La venta ya esta confirmada.')
            return redirect('ventas:venta_detail', pk=pk)

        form = VentaDetalleForm(request.POST, gym=request.user.gym)
        if form.is_valid():
            detalle = form.save(commit=False)
            detalle.venta = venta
            detalle.precio = form.cleaned_data['precio']
            detalle.save()
            venta.recalcular_total()
            messages.success(request, 'Producto agregado a la venta.')
        else:
            messages.error(request, f'Revisa los datos: {form.errors.as_text()}')
        return redirect('ventas:venta_detail', pk=pk)


class VentaDetalleDeleteView(GymRequiredMixin, View):
    def post(self, request, pk, detalle_pk):
        venta = get_object_or_404(Venta, pk=pk, gym=request.user.gym)
        if venta.estado == Venta.CONFIRMADA:
            messages.error(request, 'La venta ya esta confirmada.')
            return redirect('ventas:venta_detail', pk=pk)
        VentaDetalle.objects.filter(pk=detalle_pk, venta=venta).delete()
        venta.recalcular_total()
        messages.success(request, 'Producto eliminado de la venta.')
        return redirect('ventas:venta_detail', pk=pk)


class VentaConfirmarView(GymRequiredMixin, View):
    """Confirmar venta => InventarioSucursal - cantidad."""

    def post(self, request, pk):
        venta = get_object_or_404(Venta, pk=pk, gym=request.user.gym)
        with transaction.atomic():
            ok, mensaje = venta.confirmar()
        if ok:
            messages.success(request, mensaje)
        else:
            messages.error(request, mensaje)
        return redirect('ventas:venta_detail', pk=pk)
