from django import forms
import re
from dataSoft.mongodb.mongo import personajes_collection

class PersonajeForm(forms.Form):
    nombre = forms.CharField(
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Aatrox, Lee Sin, Kai\'Sa'}),
        help_text='Los datos de habilidades, iconos y estadísticas se obtendrán automáticamente de Riot Games.'
    )
    tier = forms.ChoiceField(
        choices=[
            ('S', 'Tier S'),
            ('A', 'Tier A'),
            ('B', 'Tier B'),
            ('C', 'Tier C'),
            ('D', 'Tier D')
        ],
        widget=forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
        required=True,
        initial='B',
        label='Tier'
    )
    parche = forms.CharField(
        max_length=10, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 14.10'})
    )
    roles = forms.MultipleChoiceField(
        choices=[
            ('Top', 'Top'),
            ('Jungle', 'Jungla (Jungle)'),
            ('Mid', 'Mid'),
            ('Adc', 'Tirador (Adc)'),
            ('Support', 'Soporte (Support)')
        ],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        initial=['Top'],
        label='Roles / Carriles de Juego'
    )
    riot_roles = forms.MultipleChoiceField(
        choices=[
            ('Assassin', 'Asesino (Assassin)'),
            ('Fighter', 'Luchador (Fighter)'),
            ('Mage', 'Mago (Mage)'),
            ('Marksman', 'Tirador (Marksman)'),
            ('Support', 'Soporte (Support)'),
            ('Tank', 'Tanque (Tank)')
        ],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        initial=['Fighter'],
        label='Clases / Utilidades de Riot'
    )
    dificultad = forms.ChoiceField(
        choices=[
            ('Baja', 'Baja (1-3)'),
            ('Media', 'Media (4-7)'),
            ('Alta', 'Alta (8-10)')
        ],
        widget=forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
        required=True,
        initial='Media',
        label='Dificultad de Juego'
    )
    tipo_dano = forms.ChoiceField(
        choices=[
            ('Físico', 'Físico (Physical AD)'),
            ('Mágico', 'Mágico (Magic AP)'),
            ('Híbrido', 'Híbrido (Hybrid)'),
            ('Verdadero', 'Verdadero (True Damage)')
        ],
        widget=forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
        required=True,
        initial='Físico',
        label='Tipo de Daño'
    )

    def __init__(self, *args, **kwargs):
        self.original_nombre = kwargs.pop('original_nombre', None)
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        
        # 1. Validar que no contenga caracteres inválidos en nombres de LoL
        # Permitimos letras, espacios, y apóstrofe/punto (ej: Kai'Sa, Dr. Mundo, Jarvan IV)
        if not re.match(r"^[a-zA-Z\s'\.]+$", nombre):
            raise forms.ValidationError("El nombre contiene caracteres inválidos. Solo se permiten letras, espacios, puntos y apóstrofes.")

        # 2. Validación de Unicidad en MongoDB
        if personajes_collection is None:
            raise forms.ValidationError("La base de datos MongoDB no está disponible o está desconectada. Por favor, asegúrate de que el servicio de MongoDB esté iniciado.")

        if not self.original_nombre or nombre.lower() != self.original_nombre.lower():
            if personajes_collection.find_one({"nombre": {"$regex": f"^{re.escape(nombre)}$", "$options": "i"}}):
                raise forms.ValidationError(f"El campeón '{nombre}' ya existe en la base de datos.")
            
            # 3. Validación de Existencia en la API de Riot Games
            from .services import fetch_champion_data
            lol_data = fetch_champion_data(nombre)
            if not lol_data:
                raise forms.ValidationError(f"No se encontró el campeón '{nombre}' en la API oficial de Riot Games. Verifica que esté bien escrito (ej: 'Kai'Sa', 'Cho'Gath', 'Nunu & Willump' se escribe 'Nunu').")
            
            # Almacenar en caché para evitar consultas redundantes en la vista
            self.cleaned_data['lol_data'] = lol_data
            
        return nombre

    def clean_tier(self):
        tier = self.cleaned_data.get('tier', '').strip().upper()
        allowed_tiers = ['S', 'A', 'B', 'C', 'D']
        
        if tier not in allowed_tiers:
            raise forms.ValidationError(f"Tier no válido. Debe ser uno de los siguientes: {', '.join(allowed_tiers)}")
        return tier

    def clean_parche(self):
        parche = self.cleaned_data.get('parche', '').strip()
        
        # Debe tener formato de versión de LoL como "14.10" o "14.9.1"
        if not re.match(r'^\d+\.\d+(\.\d+)?$', parche):
            raise forms.ValidationError("El parche debe tener un formato de versión válido (ej: '14.10' o '14.9.1').")
        return parche

