from django import forms

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.forms import GymModelForm
from core.models import Sucursal


class ClienteForm(GymModelForm):
    class Meta:
        model = Cliente
        fields = [
            'nombre',
            'sucursal',
            'telefono',
            'correo',
            'sexo',
            'fecha_nacimiento',
            'foto',
            'nombre_contacto_emergencia',
            'telefono_contacto_emergencia',
        ]
        widgets = {'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'})}


class MembresiaForm(GymModelForm):
    class Meta:
        model = Membresia
        fields = ['nombre', 'precio', 'duracion_dias', 'descripcion']


class ClienteMembresiaForm(GymModelForm):
    """
    Venta de membresia: el cobro queda registrado aqui, sin tabla Pago.

    Quien llega a comprar suele ser cliente nuevo, asi que el desplegable trae
    al lado un boton que abre un modal para darlo de alta sin abandonar la
    venta. El cliente se crea al guardar, no antes.
    """

    #: Valor del desplegable cuando el cliente se acaba de capturar en el modal.
    NUEVO = '__nuevo__'

    cliente = forms.CharField(label='Cliente', widget=forms.Select)
    cliente_nuevo_nombre = forms.CharField(
        max_length=150, required=False, widget=forms.HiddenInput
    )
    cliente_nuevo_telefono = forms.CharField(
        max_length=30, required=False, widget=forms.HiddenInput
    )
    cliente_nuevo_sucursal = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ClienteMembresia
        fields = [
            'cliente',
            'membresia',
            'inicio',
            'precio',
            'descuento',
            'metodo_pago',
            'observaciones',
        ]
        widgets = {'inicio': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['precio'].required = False
        self.fields['precio'].help_text = 'Si lo dejas vacio se toma el de la membresia.'
        self.fields['cliente'].widget.choices = self._opciones()
        if self.instance.pk and self.instance.cliente_id:
            self.initial['cliente'] = str(self.instance.cliente_id)

    @property
    def sucursales(self):
        return Sucursal.objects.filter(gym=self.gym, activo=True).order_by('nombre')

    def _opciones(self):
        opciones = [('', 'Elige un cliente')]
        if self.gym is None:
            return opciones
        opciones += [
            (str(pk), nombre)
            for pk, nombre in Cliente.objects.filter(gym=self.gym, activo=True)
            .order_by('nombre')
            .values_list('pk', 'nombre')
        ]
        # Si el formulario se remuestra por un error, el capturado sigue en la lista.
        pendiente = (self.data.get('cliente_nuevo_nombre') or '').strip()
        if pendiente:
            opciones.append((self.NUEVO, pendiente))
        return opciones

    def clean(self):
        datos = super().clean()
        membresia = datos.get('membresia')
        if membresia and not datos.get('precio'):
            datos['precio'] = membresia.precio

        valor = datos.get('cliente')
        if not valor:
            datos.pop('cliente', None)
            return datos

        if valor == self.NUEVO:
            if not (datos.get('cliente_nuevo_nombre') or '').strip():
                self.add_error('cliente', 'Escribe el nombre del cliente.')
                datos.pop('cliente', None)
                return datos
            sucursal = self._sucursal(datos.get('cliente_nuevo_sucursal'))
            if sucursal is None:
                self.add_error('cliente', 'Elige la sucursal del cliente.')
                datos.pop('cliente', None)
                return datos
        else:
            sucursal = None

        # Con errores en otros campos no se crea a nadie: el formulario se
        # remuestra y el cliente se creara en el siguiente intento.
        if self.errors:
            datos.pop('cliente', None)
            return datos

        if sucursal is not None:
            datos['cliente'] = Cliente.objects.create(
                gym=self.gym,
                sucursal=sucursal,
                nombre=datos['cliente_nuevo_nombre'].strip(),
                telefono=(datos.get('cliente_nuevo_telefono') or '').strip(),
            )
        else:
            elegido = Cliente.objects.filter(
                pk=valor, gym=self.gym, activo=True
            ).first()
            if elegido is None:
                self.add_error('cliente', 'Elige un cliente de la lista.')
                datos.pop('cliente', None)
            else:
                datos['cliente'] = elegido
        return datos

    def _sucursal(self, valor):
        """Con una sola sucursal no se pregunta: se toma esa."""
        sucursales = self.sucursales
        if valor:
            return sucursales.filter(pk=valor).first()
        return sucursales.first() if sucursales.count() == 1 else None

    def _get_validation_exclusions(self):
        exclusiones = super()._get_validation_exclusions()
        if not isinstance(self.cleaned_data.get('cliente'), Cliente):
            exclusiones.add('cliente')
        return exclusiones


class AsistenciaForm(GymModelForm):
    class Meta:
        model = Asistencia
        fields = ['cliente', 'sucursal', 'entrenamiento', 'tipo']
