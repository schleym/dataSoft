"""dataSoft URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from leagueOfLegends import views
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name="inicio"),
    path('campeones/', views.campeones, name="campeones"),
    path('campeon/<str:pk>/', views.campeon_detalle, name="campeon_detalle"),
    
    # Autenticación
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='inicio'), name='logout'),
    path('registro/', views.registro, name='registro'),

    # CRUD para Personajes
    path('gestion/', views.gestion_campeones, name="gestion_campeones"),
    path('gestion/crear/', views.campeon_crear, name="campeon_crear"),
    path('gestion/editar/<str:pk>/', views.campeon_editar, name="campeon_editar"),
    path('gestion/eliminar/<str:pk>/', views.campeon_eliminar, name="campeon_eliminar"),

    # Nuevas Secciones
    path('tierlist/', views.tierlist, name="tierlist"),
    path('revisor/', views.revisor_champion_pool, name="revisor"),
    path('estadisticas/', views.estadisticas, name="estadisticas"),
    path('leaderboard/', views.leaderboard, name="leaderboard"),
    path('buscar/', views.buscar, name="buscar"),
    path('buscar-sugerencias/', views.buscar_sugerencias, name="buscar_sugerencias"),

    # Transacciones MongoDB
    path('transaccion/tier/<str:pk>/', views.transaccion_cambio_tier, name="transaccion_cambio_tier"),
    path('transaccion/partida/<str:pk>/', views.transaccion_registrar_partida, name="transaccion_registrar_partida"),

    # Reportes MongoDB
    path('reporte/historial-tier/', views.reporte_historial_tier, name='reporte_historial_tier'),
    path('reporte/partidas/', views.reporte_partidas_analizadas, name='reporte_partidas_analizadas'),

    # Perfiles de Usuario y Acciones Personalizadas
    path('usuario/<str:username>/', views.perfil_usuario, name='perfil_usuario'),
    path('usuario/tier/guardar/<str:champ_id>/', views.guardar_tier_comentario, name='guardar_tier_comentario'),
    path('partida/editar/<str:partida_id>/', views.editar_partida, name='editar_partida'),
    path('partida/eliminar/<str:partida_id>/', views.eliminar_partida, name='eliminar_partida'),

    # Nuevas interacciones de usuarios normales
    path('campeon/<str:pk>/votar/', views.votar_tier, name='votar_tier'),
    path('campeon/<str:pk>/comentar/', views.comentar_campeon, name='comentar_campeon'),
    path('campeon/<str:pk>/favorito/', views.toggle_favorito, name='toggle_favorito'),
    path('comentario/<str:comentario_id>/eliminar/', views.eliminar_comentario_publico, name='eliminar_comentario_publico'),
]
