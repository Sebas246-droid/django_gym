from django import forms
from django.utils.html import format_html, format_html_join

from core.forms import GymModelForm, SinSufijoMixin
from core.models import Sucursal
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


class ConSugerencias(forms.TextInput):
    """
    Caja de texto con lista desplegable de valores ya usados. Es un datalist
    del navegador: se escoge uno de la lista o se escribe algo que no esta.
    """

    def __init__(self, sugerencias=(), attrs=None):
        self.sugerencias = sugerencias
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        lista = f'{name}-sugerencias'
        attrs = {**(attrs or {}), 'list': lista, 'autocomplete': 'off'}
        opciones = format_html_join(
            '', '<option value="{}"></option>', ((s,) for s in self.sugerencias)
        )
        return format_html(
            '{}<datalist id="{}">{}</datalist>',
            super().render(name, value, attrs, renderer),
            lista,
            opciones,
        )


class ProductoForm(GymModelForm):
    """
    La categoria es un solo campo: despliega las que ya existen y acepta una
    que no este, creandola junto con el producto.
    """

    categoria = forms.CharField(
        max_length=120,
        label='Categoria',
        help_text='Elige una de la lista o escribe una nueva.',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].widget = ConSugerencias(
            sugerencias=self._existentes(),
            attrs={'placeholder': 'Ej. Suplementos'},
        )
        # Al editar, el campo llega con el id de la categoria: se cambia por su
        # nombre, que es lo que la caja de texto sabe mostrar.
        if self.instance.pk and self.instance.categoria_id:
            self.initial['categoria'] = self.instance.categoria.nombre

    def _existentes(self):
        if self.gym is None:
            return []
        return list(
            CategoriaProducto.objects.filter(gym=self.gym, activo=True)
            .order_by('nombre')
            .values_list('nombre', flat=True)
        )

    def clean_categoria(self):
        return (self.cleaned_data['categoria'] or '').strip()

    def _verificar_codigo(self, codigo):
        """
        Se adelanta a la comprobacion de unicidad de Django, que corre despues
        de clean(), para no dejar una categoria creada cuando el alta va a
        fallar igual. Marcar aqui el error hace ademas que Django no repita el
        mismo aviso mas abajo.
        """
        if not codigo or self.gym is None:
            return
        otros = Producto.objects.filter(gym=self.gym, codigo=codigo)
        if self.instance.pk:
            otros = otros.exclude(pk=self.instance.pk)
        if otros.exists():
            self.add_error('codigo', 'Ya existe un producto con ese codigo.')

    def clean(self):
        datos = super().clean()
        self._verificar_codigo(datos.get('codigo'))
        nombre = datos.get('categoria')
        if not nombre:
            return datos
        if self.errors:
            # Algo mas viene mal: no se crea la categoria todavia. Se saca del
            # diccionario porque el modelo espera un objeto, no el texto.
            datos.pop('categoria', None)
            return datos
        datos['categoria'] = self._categoria(nombre)
        return datos

    def _get_validation_exclusions(self):
        exclusiones = super()._get_validation_exclusions()
        # Cuando el alta ya trae errores la categoria se queda sin resolver a
        # proposito. Sin esto el modelo agrega un 'no puede ser nulo' que solo
        # estorba, encima del error de verdad.
        if not isinstance(self.cleaned_data.get('categoria'), CategoriaProducto):
            exclusiones.add('categoria')
        return exclusiones

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


class ProductoAltaForm(ProductoForm):
    """
    Alta de producto con sus existencias iniciales. Dar de alta algo que ya
    tienes en la bodega es, en los hechos, una compra: por eso la cantidad se
    pide aqui y la vista levanta la compra correspondiente, en vez de obligar a
    recorrer producto -> compra -> linea -> confirmar.
    """

    cantidad = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label='Cantidad inicial',
        help_text='Cuantas piezas entran ahora. Dejalo en 0 si aun no tienes.',
    )
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.none(),
        required=False,
        label='Sucursal que las recibe',
    )
    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.none(),
        required=False,
        label='Proveedor',
        empty_label='Sin proveedor',
        help_text='Opcional: solo para dejar constancia de a quien se le compro.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sucursales = Sucursal.objects.filter(gym=self.gym, activo=True)
        self.fields['sucursal'].queryset = sucursales
        self.fields['proveedor'].queryset = Proveedor.objects.filter(
            gym=self.gym, activo=True
        )
        # Con una sola sucursal no tiene sentido preguntar: se elige sola.
        if sucursales.count() == 1:
            self.fields['sucursal'].initial = sucursales.first()
            self.fields['sucursal'].widget = forms.HiddenInput()

    def clean(self):
        datos = super().clean()
        cantidad = datos.get('cantidad') or 0
        if not cantidad or datos.get('sucursal'):
            return datos

        if not self.fields['sucursal'].queryset.exists():
            raise forms.ValidationError(
                'Para cargar existencias necesitas al menos una sucursal. '
                'Da de alta una en Sucursales y vuelve a intentarlo.'
            )
        if self.fields['sucursal'].widget.is_hidden:
            # Oculto no puede mostrar su propio error: se manda al aviso de arriba.
            raise forms.ValidationError('Indica a que sucursal entran las piezas.')
        self.add_error('sucursal', 'Indica a que sucursal entran las piezas.')
        return datos

    # La plantilla pinta los campos en dos bloques: la ficha del producto y lo
    # que entra a la bodega.
    EXISTENCIAS = ('cantidad', 'sucursal', 'proveedor')

    def ficha(self):
        return [c for c in self if c.name not in self.EXISTENCIAS]

    def existencias(self):
        return [self[nombre] for nombre in self.EXISTENCIAS]


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
