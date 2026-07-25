from django import forms

from core.forms import GymModelForm, SinSufijoMixin
from inventario.models import Producto
from ventas.models import Venta, VentaDetalle


class VentaForm(GymModelForm):
    class Meta:
        model = Venta
        fields = ['sucursal', 'cliente', 'metodo_pago', 'descuento']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].required = False
        self.fields['cliente'].help_text = 'Opcional: venta de mostrador.'


class VentaDetalleForm(SinSufijoMixin, forms.ModelForm):
    class Meta:
        model = VentaDetalle
        fields = ['producto', 'cantidad', 'precio']

    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(gym=gym, activo=True)
        self.fields['precio'].required = False

    def clean(self):
        datos = super().clean()
        producto = datos.get('producto')
        if producto and not datos.get('precio'):
            datos['precio'] = producto.precio_venta
        return datos
