from django import forms

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


class ProductoForm(GymModelForm):
    """
    La categoria se elige de una lista. Cuando falta una, el boton de al lado
    abre un modal para capturarla: se agrega a la lista y se crea al guardar,
    sin perder lo que ya se llevaba escrito del producto.
    """

    #: Valor que toma el desplegable cuando la categoria se acaba de capturar
    #: en el modal y todavia no existe en la base.
    NUEVA = '__nueva__'

    categoria = forms.CharField(label='Categoria', widget=forms.Select)
    categoria_nueva = forms.CharField(
        max_length=120, required=False, widget=forms.HiddenInput
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
        self.fields['categoria'].widget.choices = self._opciones()
        # Al editar, el campo llega con el objeto: el desplegable trabaja con ids.
        if self.instance.pk and self.instance.categoria_id:
            self.initial['categoria'] = str(self.instance.categoria_id)

    def _opciones(self):
        opciones = [('', 'Elige una categoria')]
        if self.gym is None:
            return opciones
        opciones += [
            (str(pk), nombre)
            for pk, nombre in CategoriaProducto.objects.filter(
                gym=self.gym, activo=True
            )
            .order_by('nombre')
            .values_list('pk', 'nombre')
        ]
        # Al reenviar un formulario con errores hay que conservar la categoria
        # capturada en el modal, o el desplegable la perderia.
        pendiente = (self.data.get('categoria_nueva') or '').strip()
        if pendiente:
            opciones.append((self.NUEVA, pendiente))
        return opciones

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

        valor = datos.get('categoria')
        if not valor:
            datos.pop('categoria', None)
            return datos

        if valor == self.NUEVA:
            nombre = (datos.get('categoria_nueva') or '').strip()
            if not nombre:
                self.add_error('categoria', 'Escribe el nombre de la categoria.')
                datos.pop('categoria', None)
                return datos
        else:
            nombre = None

        # Con errores en otros campos no se crea nada: el formulario se
        # remuestra y la categoria se creara en el siguiente intento. Se saca
        # del diccionario porque el modelo espera un objeto, no el texto.
        if self.errors:
            datos.pop('categoria', None)
            return datos

        if nombre is not None:
            datos['categoria'] = self._categoria(nombre)
        else:
            elegida = CategoriaProducto.objects.filter(
                pk=valor, gym=self.gym, activo=True
            ).first()
            if elegida is None:
                self.add_error('categoria', 'Elige una categoria de la lista.')
                datos.pop('categoria', None)
            else:
                datos['categoria'] = elegida
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

    # La plantilla pinta los campos en dos bloques: la ficha del producto y lo
    # que entra a la bodega. Al editar solo existe el primero.
    EXISTENCIAS = ()

    def ficha(self):
        return [c for c in self if c.name not in self.EXISTENCIAS]

    def existencias(self):
        return [self[nombre] for nombre in self.EXISTENCIAS]


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

    EXISTENCIAS = ('cantidad', 'sucursal', 'proveedor')


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
