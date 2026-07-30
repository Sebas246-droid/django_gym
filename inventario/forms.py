import json

from django import forms
from django.urls import reverse
from django.utils.html import format_html

from core.forms import GymModelForm, SinSufijoMixin
from core.models import Sucursal
from inventario.models import (
    CategoriaProducto,
    InventarioSucursal,
    Movimiento,
    Producto,
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

        repetido = otros.first()
        if repetido is None:
            return
        # Casi siempre no es un error de captura: llego mas de algo que ya se
        # vende. Frenar sin decir a donde ir deja a la persona atorada.
        self.add_error(
            'codigo',
            format_html(
                'Ya tienes <b>{}</b> con ese codigo. Si te llego mas, '
                'registralo como <a href="{}?producto={}">entrada</a>.',
                repetido.nombre,
                reverse('inventario:movimiento_create'),
                repetido.pk,
            ),
        )

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
    tienes en la bodega es, en los hechos, una entrada: por eso la cantidad se
    pide aqui y la vista deja su movimiento, en vez de mandar a registrarlo
    despues en otra pantalla.
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sucursales = Sucursal.objects.filter(gym=self.gym, activo=True)
        self.fields['sucursal'].queryset = sucursales
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

    EXISTENCIAS = ('cantidad', 'sucursal')


class InventarioSucursalForm(SinSufijoMixin, forms.ModelForm):
    """Ajuste manual de stock minimo / existencias iniciales."""

    class Meta:
        model = InventarioSucursal
        fields = ['stock', 'stock_minimo']


class SelectorDeProducto(forms.Select):
    """
    Desplegable que carga en cada opcion el costo y el precio del producto,
    para que la pantalla pueda prellenar el importe al elegirlo.
    """

    def __init__(self, productos=(), attrs=None):
        self.precios = {
            str(p.pk): (p.precio_compra, p.precio_venta, p.codigo) for p in productos
        }
        super().__init__(attrs)

    def create_option(self, name, value, *args, **kwargs):
        opcion = super().create_option(name, value, *args, **kwargs)
        datos = self.precios.get(str(value))
        if datos:
            compra, venta, codigo = datos
            opcion['attrs'].update({
                'data-compra': compra,
                'data-venta': venta,
                'data-codigo': codigo,
            })
        return opcion


class MovimientoForm(SinSufijoMixin, forms.Form):
    """
    Lo que entra o sale a mano. La venta no se registra aqui: la anota el punto
    de venta al cobrar, y dejarla a mano abriria la puerta a contarla dos veces.
    """

    MOTIVOS_A_MANO = [
        m for m in Movimiento.MOTIVOS if m[0] != Movimiento.VENTA
    ]

    producto = forms.ModelChoiceField(
        queryset=Producto.objects.none(),
        label='Producto',
        empty_label='Elige el producto',
    )
    tipo = forms.ChoiceField(choices=Movimiento.TIPOS, label='Entra o sale')
    motivo = forms.ChoiceField(choices=MOTIVOS_A_MANO, label='Motivo')
    cantidad = forms.IntegerField(min_value=1, label='Cuantas piezas')
    precio = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=0,
        label='Importe por pieza',
        help_text='Vacio toma el del producto: su costo si entra, su precio si sale.',
    )
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.none(), label='Sucursal'
    )
    nota = forms.CharField(max_length=200, required=False, label='Nota (opcional)')

    def __init__(self, *args, gym=None, inicial_producto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.gym = gym

        productos = Producto.objects.filter(gym=gym, activo=True).order_by('nombre')
        self.fields['producto'].queryset = productos
        self.fields['producto'].widget = SelectorDeProducto(productos=productos)
        self.fields['producto'].widget.choices = self.fields['producto'].choices
        if inicial_producto and not self.is_bound:
            self.fields['producto'].initial = inicial_producto

        sucursales = Sucursal.objects.filter(gym=gym, activo=True)
        self.fields['sucursal'].queryset = sucursales
        if sucursales.count() == 1:
            self.fields['sucursal'].initial = sucursales.first()
            self.fields['sucursal'].widget = forms.HiddenInput()

    # Los lee la plantilla para esconder los motivos que no aplican al tipo
    # elegido: una merma no es una entrada.
    @property
    def MOTIVOS_ENTRADA_JSON(self):
        return json.dumps(Movimiento.MOTIVOS_ENTRADA)

    @property
    def MOTIVOS_SALIDA_JSON(self):
        return json.dumps(
            [m for m in Movimiento.MOTIVOS_SALIDA if m != Movimiento.VENTA]
        )

    def clean(self):
        datos = super().clean()
        tipo, motivo = datos.get('tipo'), datos.get('motivo')
        if not tipo or not motivo:
            return datos

        permitidos = (
            Movimiento.MOTIVOS_ENTRADA
            if tipo == Movimiento.ENTRADA
            else Movimiento.MOTIVOS_SALIDA
        )
        if motivo not in permitidos:
            etiquetas = dict(Movimiento.MOTIVOS)
            self.add_error(
                'motivo',
                f'{etiquetas[motivo]} no aplica a una '
                f'{dict(Movimiento.TIPOS)[tipo].lower()}.',
            )
            return datos

        self._verificar_existencias(datos)
        return datos

    def _verificar_existencias(self, datos):
        """No se puede sacar mas de lo que hay: el stock quedaria en negativo."""
        if datos.get('tipo') != Movimiento.SALIDA:
            return
        producto, sucursal = datos.get('producto'), datos.get('sucursal')
        cantidad = datos.get('cantidad')
        if not producto or not sucursal or not cantidad:
            return

        hay = producto.stock_en(sucursal)
        if cantidad > hay:
            self.add_error(
                'cantidad',
                f'Solo hay {hay} de {producto.nombre} en {sucursal}.',
            )
