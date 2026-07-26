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
    """
    El alta permite estrenar categoria sin salir de la pantalla: si la que hace
    falta no esta en la lista, se escribe abajo y se crea junto con el producto.
    """

    categoria_nueva = forms.CharField(
        max_length=120,
        required=False,
        label='...o crea una categoria nueva',
        help_text='Escribela aqui si no aparece en la lista de arriba.',
        widget=forms.TextInput(attrs={'placeholder': 'Ej. Suplementos'}),
    )

    class Meta:
        model = Producto
        fields = [
            'codigo',
            'nombre',
            'categoria',
            'marca',
            'foto',
            'precio_compra',
            'precio_venta',
        ]

    # Los campos declarados se van al final; asi la caja de la categoria nueva
    # queda pegada a su lista y no despues de los precios.
    field_order = [
        'codigo',
        'nombre',
        'categoria',
        'categoria_nueva',
        'marca',
        'foto',
        'precio_compra',
        'precio_venta',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deja de ser obligatoria porque ahora se puede cubrir con el campo de texto.
        self.fields['categoria'].required = False
        self.fields['categoria'].empty_label = 'Elige una categoria'

    def clean(self):
        datos = super().clean()
        categoria = datos.get('categoria')
        nueva = (datos.get('categoria_nueva') or '').strip()

        if not categoria and not nueva:
            raise forms.ValidationError(
                'Elige una categoria de la lista o escribe una nueva.'
            )
        if categoria and nueva:
            raise forms.ValidationError(
                'Elige una categoria o escribe una nueva, pero no las dos.'
            )
        # Si algun campo ya venia mal, no se crea nada: el formulario se
        # vuelve a mostrar y la categoria se creara en el siguiente intento.
        if nueva and not self.errors:
            datos['categoria'] = self._categoria(nueva)
        return datos

    def _categoria(self, nombre):
        """Reusa la categoria si ya existe con ese nombre, sin importar mayusculas."""
        existente = CategoriaProducto.objects.filter(
            gym=self.gym, nombre__iexact=nombre
        ).first()
        if existente is None:
            return CategoriaProducto.objects.create(gym=self.gym, nombre=nombre)
        # Pudo quedar dada de baja: se reactiva en vez de duplicarla.
        if not existente.activo:
            existente.activo = True
            existente.save(update_fields=['activo', 'updated_at'])
        return existente


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
