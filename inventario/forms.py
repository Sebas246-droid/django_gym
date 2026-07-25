from django import forms

from core.forms import GymModelForm, SinSufijoMixin
from inventario.models import (
    CategoriaProducto,
    Compra,
    CompraDetalle,
    InventarioSucursal,
    Producto,
    Proveedor,
)


class CategoriaProductoForm(GymModelForm):
    class Meta:
        model = CategoriaProducto
        fields = ['nombre', 'descripcion']


class ProductoForm(GymModelForm):
    class Meta:
        model = Producto
        fields = [
            'codigo',
            'nombre',
            'categoria',
            'marca',
            'precio_compra',
            'precio_venta',
        ]


class ProveedorForm(GymModelForm):
    class Meta:
        model = Proveedor
        fields = ['nombre', 'telefono', 'correo']


class CompraForm(GymModelForm):
    class Meta:
        model = Compra
        fields = ['proveedor', 'sucursal']


class CompraDetalleForm(SinSufijoMixin, forms.ModelForm):
    class Meta:
        model = CompraDetalle
        fields = ['producto', 'cantidad', 'precio']

    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(
            gym=gym, activo=True
        )
        self.fields['precio'].required = False

    def clean(self):
        datos = super().clean()
        producto = datos.get('producto')
        if producto and not datos.get('precio'):
            datos['precio'] = producto.precio_compra
        return datos


class InventarioSucursalForm(SinSufijoMixin, forms.ModelForm):
    """Ajuste manual de stock minimo / existencias iniciales."""

    class Meta:
        model = InventarioSucursal
        fields = ['stock', 'stock_minimo']
