from core.forms import GymModelForm
from entrenamiento.models import Entrenamiento


class EntrenamientoForm(GymModelForm):
    class Meta:
        model = Entrenamiento
        fields = ['nombre', 'descripcion', 'documento', 'video']
