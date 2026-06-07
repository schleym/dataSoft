from django.db import models

class Personaje(models.Model):
    nombre = models.CharField(max_length=100)
    roles = models.JSONField()
    dificultad = models.CharField(max_length=50)
    tipo_dano = models.CharField(max_length=50)
    habilidades = models.JSONField()
    estadisticas = models.JSONField()
    builds = models.JSONField()
    runas = models.JSONField()
    hechizos = models.JSONField()
    matchups = models.JSONField()
    tier = models.CharField(max_length=2)
    parche = models.CharField(max_length=10)
    icon = models.CharField(max_length=255,null=True,blank=True)
    sprite = models.CharField(max_length=255,null=True,blank=True)
    splash = models.CharField(max_length=255,null=True,blank=True)

    def __str__(self):
        return self.nombre