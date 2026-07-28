from django import forms

from bot.models import BotTelegram
from core.forms import SinSufijoMixin


class BotTelegramForm(SinSufijoMixin, forms.ModelForm):
    class Meta:
        model = BotTelegram
        fields = ['token']
        widgets = {
            'token': forms.TextInput(
                attrs={'placeholder': '1234567890:AAF...', 'autocomplete': 'off'}
            )
        }

    def clean_token(self):
        # BotFather los entrega con el formato <id>:<clave>; validarlo aqui
        # evita ir a Telegram para descubrir un copiado a medias.
        token = (self.cleaned_data['token'] or '').strip()
        if token and ':' not in token:
            raise forms.ValidationError(
                'Ese no parece un token. Copia el que te dio BotFather completo.'
            )
        return token
