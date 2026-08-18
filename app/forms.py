from django import forms

from .models import Sitio


class SitioForm(forms.ModelForm):
    class Meta:
        model = Sitio
        fields = [
            "nombre",
            "codigo_metadatos",
            "latitud",
            "longitud",
            "sistema_referencia",
            "altitud",
            "pendiente",
            "topografia",
            "uso_actual",
            "propiedad_tierra",
            "intervenido",
            "vereda",
            "disturbio",
            "vegetacion",
            "cobertura",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
