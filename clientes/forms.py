from django import forms

from clientes.models import Asistencia, Cliente, ClienteMembresia, Membresia
from core.forms import GymModelForm


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
    """Venta de membresia: el cobro queda registrado aqui, sin tabla Pago."""

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

    def clean(self):
        datos = super().clean()
        membresia = datos.get('membresia')
        if membresia and not datos.get('precio'):
            datos['precio'] = membresia.precio
        return datos


class AsistenciaForm(GymModelForm):
    class Meta:
        model = Asistencia
        fields = ['cliente', 'sucursal', 'entrenamiento', 'tipo']
