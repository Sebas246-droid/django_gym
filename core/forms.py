from django import forms

from core.models import Gym, GymImagen, Plan, Sucursal

PALETAS = [
    ('#F5C518', '#111111', 'Amarillo sobre negro'),
    ('#E63946', '#14181D', 'Rojo energia'),
    ('#00B4D8', '#0B1A2A', 'Azul electrico'),
    ('#2DC653', '#10231A', 'Verde vitalidad'),
    ('#FF6B35', '#1A1214', 'Naranja fuego'),
    ('#B388FF', '#150F24', 'Violeta'),
]


class SinSufijoMixin:
    """Etiquetas sin los dos puntos finales que Django agrega por omision."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)


class GymModelForm(SinSufijoMixin, forms.ModelForm):
    """
    Base de todos los formularios de negocio.
    Recorta cualquier combo relacionado al gym del usuario: nunca se
    mezclan los datos entre gimnasios.
    """

    def __init__(self, *args, gym=None, **kwargs):
        self.gym = gym
        super().__init__(*args, **kwargs)
        if gym is not None:
            for field in self.fields.values():
                if isinstance(field, forms.ModelChoiceField):
                    modelo = field.queryset.model
                    nombres = {f.name for f in modelo._meta.get_fields()}
                    if 'gym' in nombres:
                        field.queryset = field.queryset.filter(gym=gym)
                        if 'activo' in nombres:
                            field.queryset = field.queryset.filter(activo=True)


class PlanForm(SinSufijoMixin, forms.ModelForm):
    class Meta:
        model = Plan
        fields = [
            'nombre',
            'precio',
            'usuarios_max',
            'clientes_max',
            'sucursales_max',
            'activo',
        ]


class GymForm(SinSufijoMixin, forms.ModelForm):
    class Meta:
        model = Gym
        fields = [
            'nombre',
            'plan',
            'telefono',
            'email',
            'logo',
            'zona_horaria',
            'moneda',
            'activo',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].queryset = Plan.objects.activos()


class SucursalForm(GymModelForm):
    class Meta:
        model = Sucursal
        fields = [
            'nombre',
            'direccion',
            'telefono',
            'correo',
            'responsable',
            'latitud',
            'longitud',
        ]
        widgets = {
            'latitud': forms.NumberInput(attrs={'step': 'any', 'placeholder': '19.432608'}),
            'longitud': forms.NumberInput(attrs={'step': 'any', 'placeholder': '-99.133209'}),
        }


class GymSitioForm(SinSufijoMixin, forms.ModelForm):
    """Configuracion de la pagina publica: colores, textos, contacto."""

    class Meta:
        model = Gym
        fields = [
            'color_primario',
            'color_secundario',
            'frase_principal',
            'descripcion',
            'portada',
            'logo',
            'telefono',
            'email',
            'sitio_publico',
        ]
        widgets = {
            'color_primario': forms.TextInput(attrs={'type': 'color'}),
            'color_secundario': forms.TextInput(attrs={'type': 'color'}),
            'descripcion': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['frase_principal'].widget.attrs['placeholder'] = Gym.FRASE_DEFAULT
        self.fields['descripcion'].widget.attrs['placeholder'] = Gym.DESCRIPCION_DEFAULT
        self.fields['frase_principal'].help_text = (
            'Si lo dejas vacio se usa la frase generica.'
        )
        self.fields['descripcion'].help_text = (
            'Si lo dejas vacio se usa la descripcion generica.'
        )


class GymImagenForm(GymModelForm):
    class Meta:
        model = GymImagen
        fields = ['imagen', 'titulo', 'orden']
