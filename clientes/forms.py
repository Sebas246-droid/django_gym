from datetime import timedelta

from django import forms
from django.utils import timezone

from clientes.models import (
    NIVELES_ACTIVIDAD,
    Asistencia,
    Cliente,
    ClienteMembresia,
    Membresia,
)
from core.forms import FechaInput, GymModelForm
from core.models import Sucursal


class ClienteForm(GymModelForm):
    """
    La ficha guarda tambien lo que necesita la calculadora de calorias. Sexo,
    nacimiento, estatura y actividad casi no cambian: capturarlos aqui hace que
    despues el bot solo tenga que preguntar el peso.
    """

    peso_kg = forms.DecimalField(
        max_digits=5,
        decimal_places=1,
        required=False,
        min_value=25,
        max_value=300,
        label='Peso de hoy (kg)',
        help_text='Se guarda como historico. Puedes dejarlo vacio.',
    )

    class Meta:
        model = Cliente
        fields = [
            'nombre',
            'sucursal',
            'telefono',
            'correo',
            'sexo',
            'fecha_nacimiento',
            'estatura_cm',
            'nivel_actividad',
            'foto',
            'nombre_contacto_emergencia',
            'telefono_contacto_emergencia',
        ]
        widgets = {'fecha_nacimiento': FechaInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Es un campo con choices, no una relacion: la opcion vacia se cambia
        # reescribiendo la lista, no con empty_label.
        self.fields['nivel_actividad'].choices = [
            ('', 'Sin especificar'), *NIVELES_ACTIVIDAD
        ]
        if self.instance.pk:
            ultimo = self.instance.medidas.first()
            if ultimo:
                self.fields['peso_kg'].initial = ultimo.peso_kg

    def save(self, commit=True):
        cliente = super().save(commit=commit)
        peso = self.cleaned_data.get('peso_kg')
        if commit and peso:
            self._registrar_peso(cliente, peso)
        return cliente

    def _registrar_peso(self, cliente, peso):
        """Un registro por dia: reeditar la ficha no llena el historico."""
        from bot.models import MedidaCorporal

        MedidaCorporal.objects.update_or_create(
            cliente=cliente,
            fecha=timezone.localdate(),
            defaults={'peso_kg': peso},
        )


class MembresiaForm(GymModelForm):
    class Meta:
        model = Membresia
        fields = ['nombre', 'precio', 'duracion_dias', 'descripcion', 'foto']


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
            'comprobante',
            'observaciones',
        ]
        widgets = {'inicio': FechaInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los dos se pueden dejar en blanco, asi que se ven en blanco: un 0
        # precargado se lee como un dato que ya esta puesto.
        self._volver_opcional(
            'precio',
            'Precio (opcional)',
            'Vacio toma el precio de la membresia.',
        )
        self._volver_opcional(
            'descuento',
            'Descuento (opcional)',
            'Vacio es sin descuento.',
        )
        self.fields['comprobante'].label = 'Comprobante (opcional)'
        self.fields['comprobante'].help_text = (
            'Foto del ticket o PDF de la transferencia. Hasta 10 MB.'
        )
        self.fields['cliente'].widget.choices = self._opciones()
        if self.instance.pk and self.instance.cliente_id:
            self.initial['cliente'] = str(self.instance.cliente_id)

    def _volver_opcional(self, nombre, etiqueta, ayuda):
        campo = self.fields[nombre]
        campo.required = False
        campo.label = etiqueta
        campo.help_text = ayuda
        # El 0 viene del valor por omision del modelo; se quita para que el
        # campo aparezca vacio y se vea que no hace falta llenarlo.
        campo.initial = None
        campo.widget.attrs['placeholder'] = '0'

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
        if membresia and datos.get('precio') is None:
            datos['precio'] = membresia.precio
        # El modelo no admite nulo en estos dos: en blanco significa cero.
        if datos.get('descuento') is None:
            datos['descuento'] = 0

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

        self._encadenar(datos)
        return datos

    def _encadenar(self, datos):
        """
        Si la nueva membresia arrancaria encima de una que sigue corriendo, se
        recorre al dia siguiente de aquella.

        Renovar antes de que se acabe la anterior es lo normal, y empezar hoy
        le borraria al socio los dias que ya tenia pagados.
        """
        cliente, inicio = datos.get('cliente'), datos.get('inicio')
        if not isinstance(cliente, Cliente) or not inicio:
            return

        anterior = (
            cliente.membresias.filter(
                activo=True, inicio__lte=inicio, fin__gte=inicio
            )
            .exclude(pk=self.instance.pk)
            .exclude(estado='cancelada')
            .order_by('-fin')
            .first()
        )
        if anterior is None:
            return

        datos['inicio'] = anterior.fin + timedelta(days=1)
        #: Lo lee la vista para avisarselo a quien esta cobrando.
        self.encadenada_tras = anterior

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
