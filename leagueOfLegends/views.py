from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .forms import PersonajeForm
from .services import fetch_champion_data, enrich_champion_data
from dataSoft.mongodb.mongo import (
    personajes_collection,
    partidas_analizadas_collection,
    comentarios_tier_usuarios_collection,
    votos_tier_collection,
    comentarios_publicos_collection,
    favoritos_collection,
)
from django.contrib.auth.models import User
from bson import ObjectId
import json
from datetime import datetime
from .riot_api import get_challenger_leaderboard

from functools import wraps

def admin_required(view_func):
    """Decorador que restringe el acceso a usuarios administradores (is_staff)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_staff:
            messages.error(request, "Acceso restringido: esta sección es solo para administradores.")
            return redirect('inicio')
        return view_func(request, *args, **kwargs)
    return wrapper

def index(request):
    try:
        # Recuperar de MongoDB
        personajes_list = list(personajes_collection.find())
        personajes = []
        for p in personajes_list:
            personajes.append(enrich_champion_data(p, personajes_list))
            
        # Cargar Top 3 del ranking
        try:
            ranking = get_challenger_leaderboard()[:3]
        except Exception as e:
            print(f"Error cargando ranking: {e}")
            ranking = []
    except Exception as e:
        messages.error(request, f"Error al cargar datos desde MongoDB: {e}")
        personajes = []
        ranking = []

    return render(request, "index.html", {
        "personajes": personajes,
        "ranking": ranking
    })

def campeones(request):
    try:
        personajes_db = list(personajes_collection.find())
        personajes = []
        for p in personajes_db:
            personajes.append(enrich_champion_data(p, personajes_db))
    except Exception as e:
        messages.error(request, f"Error al cargar campeones: {e}")
        personajes = []

    return render(request, "campeones.html", {
        "personajes": personajes
    })

def leaderboard(request):
    try:
        ranking = get_challenger_leaderboard()
    except Exception as e:
        messages.error(request, f"Error al cargar ranking de Riot Games: {e}")
        ranking = []
        
    return render(request, 'leaderboard.html', {
        'ranking': ranking
    })

def campeon_detalle(request, pk):
    try:
        obj_id = ObjectId(pk)
        personaje = personajes_collection.find_one({"_id": obj_id})
        
        if not personaje:
            messages.error(request, "Campeón no encontrado.")
            return redirect('campeones')

        # Obtener todos los personajes para matchups dinámicos
        todos_personajes = list(personajes_collection.find())
        personaje = enrich_champion_data(personaje, todos_personajes)

        # Formatear estadísticas para mostrar nombres más amigables
        stats_display = [
            {"label": "Vida", "value": personaje.get('estadisticas', {}).get('hp'), "icon": "bi-heart-fill"},
            {"label": "Armadura", "value": personaje.get('estadisticas', {}).get('armor'), "icon": "bi-shield-shaded"},
            {"label": "Res. Mágica", "value": personaje.get('estadisticas', {}).get('spellblock'), "icon": "bi-magic"},
            {"label": "Rango", "value": personaje.get('estadisticas', {}).get('attackrange'), "icon": "bi-arrows-expand"},
            {"label": "Velocidad", "value": personaje.get('estadisticas', {}).get('movespeed'), "icon": "bi-speedometer2"},
        ]

        # ── NUEVAS INTERACCIONES DE USUARIOS ──────────────────────────────────

        # Votos de Tier de la Comunidad
        todos_votos = list(votos_tier_collection.find({"campeon_id": obj_id}))
        conteo_votos = {t: 0 for t in ['S', 'A', 'B', 'C', 'D']}
        for v in todos_votos:
            t = v.get('tier', '').upper()
            if t in conteo_votos:
                conteo_votos[t] += 1
        total_votos = sum(conteo_votos.values())
        # Tier más votado por la comunidad
        tier_comunidad = max(conteo_votos, key=conteo_votos.get) if total_votos > 0 else None
        # Voto del usuario actual
        mi_voto = None
        es_favorito = False
        if request.user.is_authenticated:
            voto_doc = votos_tier_collection.find_one({
                "campeon_id": obj_id, "usuario": request.user.username
            })
            mi_voto = voto_doc.get('tier') if voto_doc else None
            # Estado de favorito
            fav_doc = favoritos_collection.find_one({
                "campeon_id": obj_id, "usuario": request.user.username
            })
            es_favorito = fav_doc is not None

        # Comentarios Públicos del campeón
        comentarios_raw = list(comentarios_publicos_collection.find(
            {"campeon_id": obj_id}
        ).sort("fecha", -1).limit(50))
        staff_usernames = set(User.objects.filter(is_staff=True).values_list('username', flat=True))
        comentarios_publicos = []
        for c in comentarios_raw:
            comentarios_publicos.append({
                'id': str(c['_id']),
                'usuario': c.get('usuario', ''),
                'texto': c.get('texto', ''),
                'fecha': c.get('fecha', ''),
                'es_admin': c.get('usuario') in staff_usernames,
                'es_propio': request.user.is_authenticated and c.get('usuario') == request.user.username,
            })

        return render(request, "campeon_detalle.html", {
            "p": personaje,
            "stats_display": stats_display,
            # Interacciones nuevas
            "conteo_votos": conteo_votos,
            "total_votos": total_votos,
            "tier_comunidad": tier_comunidad,
            "mi_voto": mi_voto,
            "es_favorito": es_favorito,
            "comentarios_publicos": comentarios_publicos,
            "campeon_id": pk,
        })
    except Exception as e:
        messages.error(request, f"Error al cargar detalle: {e}")
        return redirect('campeones')

# --- CRUD Views con MongoDB y Autenticación ---

@admin_required
def gestion_campeones(request):
    try:
        personajes = list(personajes_collection.find())
        for p in personajes:
            p['id'] = str(p['_id'])
    except Exception as e:
        messages.error(request, f"Error en gestión: {e}")
        personajes = []
    return render(request, "gestion_campeones.html", {"personajes": personajes})

@admin_required
def campeon_crear(request):
    if request.method == 'POST':
        form = PersonajeForm(request.POST)
        if form.is_valid():
            nombre = form.cleaned_data['nombre']
            tier = form.cleaned_data['tier']
            parche = form.cleaned_data['parche']
            lol_data = form.cleaned_data.get('lol_data')

            try:
                if lol_data:
                    nuevo_personaje = {
                        "nombre": lol_data['nombre'],
                        "tier": tier,
                        "parche": parche,
                        "roles": form.cleaned_data['roles'],
                        "riot_roles": form.cleaned_data['riot_roles'],
                        "dificultad": form.cleaned_data['dificultad'],
                        "tipo_dano": form.cleaned_data['tipo_dano'],
                        "habilidades": lol_data['habilidades'],
                        "estadisticas": lol_data['estadisticas'],
                        "icon": lol_data['icon'],
                        "sprite": lol_data['sprite'],
                        "splash": lol_data['splash'],
                        "builds": [],
                        "runas": [],
                        "hechizos": [],
                        "matchups": {
                            "favorables": [],
                            "desfavorables": []
                        }
                    }
                    personajes_collection.insert_one(nuevo_personaje)
                    messages.success(request, f"Campeón '{nombre}' creado exitosamente en MongoDB con datos de Riot.")
                    return redirect('gestion_campeones')
                else:
                    messages.error(request, "Error de sincronización con Riot Games API.")
            except Exception as e:
                messages.error(request, f"Error al insertar en MongoDB: {e}")
    else:
        form = PersonajeForm()
    return render(request, 'formulario_campeon.html', {'form': form, 'titulo': 'Crear Campeón'})

@admin_required
def campeon_editar(request, pk):
    try:
        obj_id = ObjectId(pk)
        personaje = personajes_collection.find_one({"_id": obj_id})
        if not personaje:
            messages.error(request, "Campeón no encontrado.")
            return redirect('gestion_campeones')
    except:
        messages.error(request, "ID no válido.")
        return redirect('gestion_campeones')

    if request.method == 'POST':
        form = PersonajeForm(request.POST, original_nombre=personaje['nombre'])
        if form.is_valid():
            try:
                nombre = form.cleaned_data['nombre']
                update_data = {
                    "nombre": nombre,
                    "tier": form.cleaned_data['tier'],
                    "parche": form.cleaned_data['parche'],
                    "roles": form.cleaned_data['roles'],
                    "riot_roles": form.cleaned_data['riot_roles'],
                    "dificultad": form.cleaned_data['dificultad'],
                    "tipo_dano": form.cleaned_data['tipo_dano']
                }
                
                # Sincronizar datos de Riot si el nombre cambió y el validador cacheó los datos
                lol_data = form.cleaned_data.get('lol_data')
                if lol_data and nombre.lower() != personaje['nombre'].lower():
                    update_data.update({
                        "riot_roles": lol_data['roles'],
                        "habilidades": lol_data['habilidades'],
                        "estadisticas": lol_data['estadisticas'],
                        "icon": lol_data['icon'],
                        "sprite": lol_data['sprite'],
                        "splash": lol_data['splash'],
                    })
                
                # Si el personaje no tiene 'riot_roles' guardado, traerlo de la API para mantener consistencia
                if 'riot_roles' not in personaje and 'riot_roles' not in update_data:
                    from .services import fetch_champion_data
                    lol_data_fallback = fetch_champion_data(nombre)
                    if lol_data_fallback:
                        update_data["riot_roles"] = lol_data_fallback['roles']

                personajes_collection.update_one({"_id": obj_id}, {"$set": update_data})
                messages.success(request, f"Campeón '{nombre}' actualizado.")
                return redirect('gestion_campeones')
            except Exception as e:
                messages.error(request, f"Error al actualizar: {e}")
    else:
        # Pre-poblar el formulario con campos avanzados
        initial_data = {
            "nombre": personaje['nombre'],
            "tier": personaje['tier'],
            "parche": personaje['parche'],
            "roles": personaje.get('roles', []),
            "riot_roles": personaje.get('riot_roles', []),
            "dificultad": personaje.get('dificultad', 'Media'),
            "tipo_dano": personaje.get('tipo_dano', 'Físico')
        }
        form = PersonajeForm(initial=initial_data, original_nombre=personaje['nombre'])
    
    return render(request, 'formulario_campeon.html', {'form': form, 'titulo': 'Editar Campeón', 'personaje': personaje})

@admin_required
def campeon_eliminar(request, pk):
    try:
        obj_id = ObjectId(pk)
        personaje = personajes_collection.find_one({"_id": obj_id})
        if not personaje:
            messages.error(request, "Campeón no encontrado.")
            return redirect('gestion_campeones')
            
        if request.method == 'POST':
            personajes_collection.delete_one({"_id": obj_id})
            messages.success(request, f"Campeón '{personaje['nombre']}' eliminado de MongoDB.")
            return redirect('gestion_campeones')
    except Exception as e:
        messages.error(request, f"Error al eliminar: {e}")
        return redirect('gestion_campeones')
        
    return render(request, 'confirmar_eliminar.html', {'personaje': personaje})

# --- OTRAS SECCIONES (También usando MongoDB) ---

def tierlist(request):
    try:
        personajes_list = list(personajes_collection.find())
        personajes = []
        for p in personajes_list:
            personajes.append(enrich_champion_data(p, personajes_list))
            
        tier_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        
        # Enriquecer los oponentes simplificados para la tabla (tomar los 2 mejores/peores)
        for p in personajes:
            p['counters_favorables'] = p['matchup_details']['favorables'][:2]
            p['counters_desfavorables'] = p['matchup_details']['desfavorables'][:2]
            
        # Ordenar por Tier (S > A > B...) y secundariamente por Winrate descendente
        personajes_sorted = sorted(personajes, key=lambda x: (
            tier_order.get(x.get('tier', 'B'), 99),
            -x.get('estadisticas', {}).get('winrate', 50.0)
        ))
        
        # Enriquecer la posición/rank
        for i, p in enumerate(personajes_sorted, 1):
            p['posicion'] = i
            
        tiers = {
            'S': [p for p in personajes_sorted if p.get('tier') == 'S'],
            'A': [p for p in personajes_sorted if p.get('tier') == 'A'],
            'B': [p for p in personajes_sorted if p.get('tier') == 'B'],
            'C': [p for p in personajes_sorted if p.get('tier') == 'C'],
            'D': [p for p in personajes_sorted if p.get('tier') == 'D'],
        }
    except Exception as e:
        messages.error(request, f"Error en TierList: {e}")
        personajes_sorted = []
        tiers = {}
        
    return render(request, 'tierlist.html', {
        'tiers': tiers,
        'personajes': personajes_sorted
    })

def revisor_champion_pool(request):
    try:
        personajes_list = list(personajes_collection.find())
        personajes_list = sorted(personajes_list, key=lambda x: x.get('nombre', ''))
        for p in personajes_list: p['id'] = str(p['_id'])
        
        selected_ids = request.GET.getlist('champions')
        analysis = None
        
        if selected_ids:
            # Convertir IDs de string a ObjectId
            obj_ids = [ObjectId(sid) for sid in selected_ids if ObjectId.is_valid(sid)]
            selected_champs = list(personajes_collection.find({"_id": {"$in": obj_ids}}))
            
            # Lógica de conteo sobre la lista de diccionarios usando riot_roles y fallback a roles
            ad_count = sum(1 for c in selected_champs if any(r in ['Fighter', 'Marksman', 'Assassin'] for r in c.get('riot_roles', c.get('roles', []))))
            ap_count = sum(1 for c in selected_champs if any(r in ['Mage', 'Assassin'] for r in c.get('riot_roles', c.get('roles', []))))
            tank_count = sum(1 for c in selected_champs if any(r in ['Tank', 'Support'] for r in c.get('riot_roles', c.get('roles', []))))
            
            total = len(selected_champs)
            analysis = {
                'ad_perc': (ad_count / (ad_count + ap_count) * 100) if (ad_count + ap_count) > 0 else 0,
                'ap_perc': (ap_count / (ad_count + ap_count) * 100) if (ad_count + ap_count) > 0 else 0,
                'has_initiator': tank_count > 0,
                'has_tank': tank_count > 0,
                'ad_count': ad_count,
                'ap_count': ap_count,
                'tank_count': tank_count,
                'total': total
            }
    except Exception as e:
        messages.error(request, f"Error en Revisor: {e}")
        personajes_list = []
        analysis = None

    return render(request, 'revisor.html', {
        'personajes': personajes_list,
        'selected_ids': selected_ids,
        'analysis': analysis
    })

def estadisticas(request):
    try:
        personajes_list = list(personajes_collection.find())
        personajes = []
        for p in personajes_list:
            personajes.append(enrich_champion_data(p, personajes_list))
            
        total_champs = len(personajes)
        avg_winrate = sum([p.get('estadisticas', {}).get('winrate', 0) for p in personajes]) / total_champs if total_champs > 0 else 0
        
        # Agrupar winrate y contadores por carriles competitivos (Top, Jungle, Mid, Adc, Support)
        carril_stats = {
            'Top': {'total_wr': 0.0, 'count': 0},
            'Jungle': {'total_wr': 0.0, 'count': 0},
            'Mid': {'total_wr': 0.0, 'count': 0},
            'Adc': {'total_wr': 0.0, 'count': 0},
            'Support': {'total_wr': 0.0, 'count': 0}
        }
        
        for p in personajes:
            for role in p.get('roles', []):
                role_clean = role.strip().capitalize()
                # Mapeo de sinónimos si existieran
                if role_clean == 'Jungla':
                    role_clean = 'Jungle'
                elif role_clean == 'Soporte':
                    role_clean = 'Support'
                elif role_clean == 'Tirador' or role_clean == 'Adc':
                    role_clean = 'Adc'
                
                if role_clean in carril_stats:
                    carril_stats[role_clean]['total_wr'] += p.get('estadisticas', {}).get('winrate', 50.0)
                    carril_stats[role_clean]['count'] += 1
                    
        # Calcular los promedios
        promedios_carril = []
        for carril, data in carril_stats.items():
            avg_wr = round(data['total_wr'] / data['count'], 2) if data['count'] > 0 else 50.00
            promedios_carril.append({
                'carril': carril,
                'winrate': avg_wr,
                'count': data['count']
            })
            
        # Ordenar por winrate descendente
        promedios_carril = sorted(promedios_carril, key=lambda x: -x['winrate'])
        mejor_rol = promedios_carril[0] if promedios_carril else {'carril': 'Sin datos', 'winrate': 0.0, 'count': 0}
        
        # Ordenar por orden de tier (S > A > B...) y secundariamente por winrate
        tier_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        personajes_sorted = sorted(personajes, key=lambda x: (
            tier_order.get(x.get('tier', 'C'), 99),
            -x.get('estadisticas', {}).get('winrate', 50.0)
        ))

        return render(request, 'estadisticas.html', {
            'total_champs': total_champs,
            'avg_winrate': round(avg_winrate, 2),
            'promedios_carril': promedios_carril,
            'mejor_rol': mejor_rol,
            'personajes': personajes_sorted[:10]
        })
    except Exception as e:
        messages.error(request, f"Error en estadísticas: {e}")
        return render(request, 'estadisticas.html', {})

def buscar(request):
    q = request.GET.get('q', '').strip()
    if not q:
        messages.warning(request, "Por favor introduce un término de búsqueda.")
        return redirect('inicio')
        
    # 0. ¿Es búsqueda de usuario local de Django?
    if User.objects.filter(username__iexact=q).exists():
        user_obj = User.objects.get(username__iexact=q)
        return redirect('perfil_usuario', username=user_obj.username)
        
    # Importar servicios requeridos
    from .riot_api import get_summoner_profile
    from .services import fetch_champion_data
    
    # 1. ¿Es búsqueda de invocador? (Contiene '#')
    if '#' in q:
        parts = q.split('#', 1)
        game_name = parts[0].strip()
        tag_line = parts[1].strip()
        
        # Buscar en Riot API
        summoner = get_summoner_profile(game_name, tag_line)
        if summoner and summoner.get('existe'):
            return render(request, 'perfil_invocador.html', {'s': summoner})
        else:
            messages.error(request, f"No se encontró el invocador '{q}' en el servidor LAS.")
            return redirect('inicio')
            
    # 2. ¿Es búsqueda de campeón? (Buscar en MongoDB por nombre exacto o parcial)
    import re
    # Búsqueda insensible a mayúsculas
    regex = re.compile(f"^{re.escape(q)}$", re.IGNORECASE)
    campeon = personajes_collection.find_one({"nombre": regex})
    
    if campeon:
        return redirect('campeon_detalle', pk=str(campeon['_id']))
        
    # 3. Si no está en BD, buscar en Riot Data Dragon (Autocompletado / Auto-población de BD)
    lol_data = fetch_champion_data(q)
    if lol_data:
        try:
            # Auto-poblar MongoDB
            lol_data['tier'] = 'B' # Valor por defecto
            lol_data['parche'] = '14.10'
            res = personajes_collection.insert_one(lol_data)
            messages.success(request, f"¡Se ha importado y guardado '{lol_data['nombre']}' automáticamente de Riot Games!")
            return redirect('campeon_detalle', pk=str(res.inserted_id))
        except Exception as e:
            print(f"Error auto-populating champion: {e}")
            
    # 4. Si no es campeón ni contiene '#', buscar como invocador por defecto en LAS
    summoner = get_summoner_profile(q, "LAS")
    if summoner and summoner.get('existe'):
        return render(request, 'perfil_invocador.html', {'s': summoner})
        
    messages.error(request, f"No se encontró ningún campeón o invocador con el nombre '{q}'.")
    return redirect('inicio')

from django.utils import timezone
from django.contrib.sessions.models import Session
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

@receiver(user_logged_in)
def enforce_single_active_session(sender, request, user, **kwargs):
    """
    Enforces a single active session per user. When a user logs in,
    any other existing active sessions for that user are terminated.
    """
    try:
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key
            
        # Obtener todas las sesiones que no han expirado
        active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
        for session in active_sessions:
            try:
                data = session.get_decoded()
                # Si pertenece al mismo usuario y es una sesión diferente, eliminarla
                if data.get('_auth_user_id') == str(user.id) and session.session_key != session_key:
                    session.delete()
            except Exception as inner_e:
                print(f"Error decoding/deleting concurrent session: {inner_e}")
    except Exception as e:
        print(f"Error enforcing single active session: {e}")

def buscar_sugerencias(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q and len(q) >= 2:
        import re
        regex = re.compile(re.escape(q), re.IGNORECASE)
        champs = list(personajes_collection.find({"nombre": regex}, {"nombre": 1, "icon": 1}).limit(5))
        for c in champs:
            results.append({
                'nombre': c['nombre'],
                'icon': c.get('icon', ''),
                'id': str(c['_id'])
            })
    from django.http import JsonResponse
    return JsonResponse({'sugerencias': results})


# ============================================================
# TRANSACCIÓN 1 - Relación INCRUSTADA
# Registra un cambio de tier embebiendo el historial dentro
# del propio documento del campeón en MongoDB.
# ============================================================

@admin_required
def transaccion_cambio_tier(request, pk):
    """
    TRANSACCIÓN 1 (Incrustada):
    Registra un cambio de tier directamente en el documento del campeón.
    El historial se almacena como un array embebido ('historial_tier') dentro
    del mismo documento, demostrando la relación incrustada de MongoDB.
    """
    try:
        obj_id = ObjectId(pk)
        personaje = personajes_collection.find_one({"_id": obj_id})
        if not personaje:
            messages.error(request, "Campeón no encontrado.")
            return redirect('gestion_campeones')
    except Exception:
        messages.error(request, "ID no válido.")
        return redirect('gestion_campeones')

    if request.method == 'POST':
        nuevo_tier = request.POST.get('nuevo_tier', '').strip().upper()
        motivo = request.POST.get('motivo', '').strip()
        tiers_validos = ['S', 'A', 'B', 'C', 'D']

        if nuevo_tier not in tiers_validos:
            messages.error(request, "Tier no válido. Usa S, A, B, C o D.")
            return redirect('transaccion_cambio_tier', pk=pk)

        if not motivo:
            messages.error(request, "Debes proporcionar un motivo para el cambio.")
            return redirect('transaccion_cambio_tier', pk=pk)

        tier_anterior = personaje.get('tier', 'B')

        # Registro que se incrustará dentro del documento
        registro_historial = {
            "tier_anterior": tier_anterior,
            "tier_nuevo": nuevo_tier,
            "motivo": motivo,
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "realizado_por": request.user.username
        }

        try:
            # OPERACIÓN ATÓMICA: actualiza el tier Y empuja el registro al array embebido
            personajes_collection.update_one(
                {"_id": obj_id},
                {
                    "$set": {"tier": nuevo_tier},
                    "$push": {"historial_tier": registro_historial}
                }
            )
            messages.success(
                request,
                f"Tier de '{personaje['nombre']}' actualizado de {tier_anterior} → {nuevo_tier}. "
                f"El historial ha sido embebido en el documento del campeón."
            )
            return redirect('gestion_campeones')
        except Exception as e:
            messages.error(request, f"Error al registrar el cambio de tier: {e}")

    return render(request, 'transaccion_cambio_tier.html', {'personaje': personaje})


# ============================================================
# TRANSACCIÓN 2 - Relación REFERENCIADA
# Registra una partida analizada en una colección separada,
# referenciando al campeón mediante su ObjectId.
# ============================================================

@login_required
def transaccion_registrar_partida(request, pk):
    """
    TRANSACCIÓN 2 (Referenciada):
    Registra una partida analizada en la colección 'partidas_analizadas'.
    El documento NO almacena los datos del campeón directamente; en su lugar
    almacena únicamente el 'campeon_id' (ObjectId), demostrando la relación
    referenciada de MongoDB. Para mostrar datos del campeón, se hace un lookup.
    """
    try:
        obj_id = ObjectId(pk)
        personaje = personajes_collection.find_one({"_id": obj_id})
        if not personaje:
            messages.error(request, "Campeón no encontrado.")
            return redirect('gestion_campeones')
    except Exception:
        messages.error(request, "ID no válido.")
        return redirect('gestion_campeones')

    if request.method == 'POST':
        resultado = request.POST.get('resultado', '').strip()
        duracion = request.POST.get('duracion', '').strip()
        kills = request.POST.get('kills', '0').strip()
        deaths = request.POST.get('deaths', '0').strip()
        assists = request.POST.get('assists', '0').strip()
        carril = request.POST.get('carril', '').strip()
        notas = request.POST.get('notas', '').strip()

        if resultado not in ['Victoria', 'Derrota']:
            messages.error(request, "El resultado debe ser 'Victoria' o 'Derrota'.")
            return redirect('transaccion_registrar_partida', pk=pk)

        try:
            duracion_int = int(duracion)
            kills_int = int(kills)
            deaths_int = int(deaths)
            assists_int = int(assists)
        except ValueError:
            messages.error(request, "Los valores numéricos no son válidos.")
            return redirect('transaccion_registrar_partida', pk=pk)

        # Documento en colección separada → solo guarda la REFERENCIA al campeón (campeon_id)
        partida = {
            "campeon_id": obj_id,          # ← REFERENCIA (ObjectId del campeón)
            "resultado": resultado,
            "duracion_min": duracion_int,
            "kills": kills_int,
            "deaths": deaths_int,
            "assists": assists_int,
            "carril": carril,
            "notas": notas,
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "registrado_por": request.user.username
        }

        try:
            partidas_analizadas_collection.insert_one(partida)
            messages.success(
                request,
                f"Partida con '{personaje['nombre']}' registrada exitosamente en la colección "
                f"'partidas_analizadas' con referencia al ID del campeón."
            )
            return redirect('gestion_campeones')
        except Exception as e:
            messages.error(request, f"Error al registrar la partida: {e}")

    return render(request, 'transaccion_registrar_partida.html', {
        'personaje': personaje,
        'personaje_id': str(personaje['_id']),
    })


# ============================================================
# REPORTE 1 - Relación INCRUSTADA
# Consulta el historial de cambios de tier que está embebido
# dentro de los documentos de campeones.
# ============================================================

@login_required
def reporte_historial_tier(request):
    """
    REPORTE 1 (Incrustada):
    Genera un reporte de todos los cambios de tier registrados.
    Los datos provienen del array 'historial_tier' embebido en cada
    documento de campeón. Se utiliza el pipeline de agregación de MongoDB
    para desdoblar ($unwind) el array incrustado y ordenar cronológicamente.
    """
    try:
        username_filter = request.GET.get('usuario', '').strip()
        pipeline = [
            # Solo campeones que tienen historial embebido
            {"$match": {"historial_tier": {"$exists": True, "$ne": []}}},
            # Desdoblar el array embebido (cada entrada del historial se convierte en un documento)
            {"$unwind": "$historial_tier"},
            # Proyectar los campos necesarios
            {"$project": {
                "_id": 1,
                "nombre": 1,
                "icon": 1,
                "tier_actual": "$tier",
                "tier_anterior": "$historial_tier.tier_anterior",
                "tier_nuevo": "$historial_tier.tier_nuevo",
                "motivo": "$historial_tier.motivo",
                "fecha": "$historial_tier.fecha",
                "realizado_por": "$historial_tier.realizado_por",
            }},
        ]
        
        if username_filter:
            pipeline.append({"$match": {"realizado_por": username_filter}})
            
        pipeline.append({"$sort": {"fecha": -1}})

        registros = list(personajes_collection.aggregate(pipeline))
        staff_usernames = set(User.objects.filter(is_staff=True).values_list('username', flat=True))
        
        for r in registros:
            r['campeon_id'] = str(r['_id'])
            r['es_admin'] = r.get('realizado_por') in staff_usernames

        # Estadísticas del reporte
        total_cambios = len(registros)
        campeones_afectados = len(set(r['nombre'] for r in registros))

    except Exception as e:
        messages.error(request, f"Error al generar el reporte: {e}")
        registros = []
        total_cambios = 0
        campeones_afectados = 0
        username_filter = ''

    return render(request, 'reporte_historial_tier.html', {
        'registros': registros,
        'total_cambios': total_cambios,
        'campeones_afectados': campeones_afectados,
        'username_filter': username_filter,
    })


# ============================================================
# REPORTE 2 - Relación REFERENCIADA
# Consulta la colección 'partidas_analizadas' y resuelve la
# referencia al campeón haciendo un $lookup (JOIN equivalente).
# ============================================================

@login_required
def reporte_partidas_analizadas(request):
    """
    REPORTE 2 (Referenciada):
    Genera un reporte de todas las partidas analizadas.
    Demuestra la relación referenciada: los documentos en 'partidas_analizadas'
    solo tienen el 'campeon_id'; se usa $lookup para resolver la referencia
    y obtener los datos del campeón (nombre, icon, tier) desde la colección
    'personajes', equivalente a un JOIN en bases de datos relacionales.
    """
    try:
        username_filter = request.GET.get('usuario', '').strip()
        pipeline = []
        
        if username_filter:
            pipeline.append({"$match": {"registrado_por": username_filter}})
            
        pipeline.extend([
            # $lookup → JOIN entre partidas_analizadas y personajes por campeon_id/_id
            {"$lookup": {
                "from": "personajes",
                "localField": "campeon_id",         # campo referencia en partidas_analizadas
                "foreignField": "_id",              # campo objetivo en personajes
                "as": "campeon_data"                # resultado embebido temporalmente
            }},
            # Desdoblar el array resultante del lookup (siempre tiene 1 o 0 elementos)
            {"$unwind": {"path": "$campeon_data", "preserveNullAndEmptyArrays": True}},
            # Proyectar campos finales del reporte
            {"$project": {
                "_id": 1,
                "resultado": 1,
                "duracion_min": 1,
                "kills": 1,
                "deaths": 1,
                "assists": 1,
                "carril": 1,
                "notas": 1,
                "fecha": 1,
                "registrado_por": 1,
                "campeon_nombre": "$campeon_data.nombre",
                "campeon_icon": "$campeon_data.icon",
                "campeon_tier": "$campeon_data.tier",
            }},
            {"$sort": {"fecha": -1}}
        ])

        partidas = list(partidas_analizadas_collection.aggregate(pipeline))
        staff_usernames = set(User.objects.filter(is_staff=True).values_list('username', flat=True))
        for p in partidas:
            p['id'] = str(p['_id'])
            # Calcular KDA
            deaths = p.get('deaths', 1) or 1
            p['kda'] = round((p.get('kills', 0) + p.get('assists', 0)) / deaths, 2)
            p['es_admin'] = p.get('registrado_por') in staff_usernames

        # Estadísticas del reporte
        total_partidas = len(partidas)
        victorias = sum(1 for p in partidas if p.get('resultado') == 'Victoria')
        derrotas = total_partidas - victorias
        winrate = round((victorias / total_partidas * 100), 1) if total_partidas > 0 else 0

    except Exception as e:
        messages.error(request, f"Error al generar el reporte de partidas: {e}")
        partidas = []
        total_partidas = 0
        victorias = 0
        derrotas = 0
        winrate = 0
        username_filter = ''

    return render(request, 'reporte_partidas_analizadas.html', {
        'partidas': partidas,
        'total_partidas': total_partidas,
        'victorias': victorias,
        'derrotas': derrotas,
        'winrate': winrate,
        'username_filter': username_filter,
    })


# ============================================================
# PERFIL DE USUARIO ESTILO U.GG Y ACCIONES ASOCIADAS
# ============================================================

@login_required
def perfil_usuario(request, username):
    """
    Vista de perfil u.gg para mostrar y buscar la tier list,
    historial de cambios y partidas manuales de un usuario determinado.
    """
    user_obj = get_object_or_404(User, username__iexact=username)
    
    # Obtener todos los personajes para la tier list
    personajes_db = list(personajes_collection.find())
    for p in personajes_db:
        p['id'] = str(p['_id'])
    
    # Obtener las partidas analizadas registradas por este usuario
    pipeline_partidas = [
        {"$match": {"registrado_por": user_obj.username}},
        {"$lookup": {
            "from": "personajes",
            "localField": "campeon_id",
            "foreignField": "_id",
            "as": "campeon_data"
        }},
        {"$unwind": {"path": "$campeon_data", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 1,
            "resultado": 1,
            "duracion_min": 1,
            "kills": 1,
            "deaths": 1,
            "assists": 1,
            "carril": 1,
            "notas": 1,
            "fecha": 1,
            "campeon_nombre": "$campeon_data.nombre",
            "campeon_icon": "$campeon_data.icon",
            "campeon_tier": "$campeon_data.tier",
        }},
        {"$sort": {"fecha": -1}}
    ]
    partidas = list(partidas_analizadas_collection.aggregate(pipeline_partidas))
    for p in partidas:
        p['id'] = str(p['_id'])
        deaths = p.get('deaths', 1) or 1
        p['kda'] = round((p.get('kills', 0) + p.get('assists', 0)) / deaths, 2)
        
    # Obtener estadísticas agregadas del perfil
    total_partidas = len(partidas)
    victorias = sum(1 for p in partidas if p.get('resultado') == 'Victoria')
    derrotas = total_partidas - victorias
    winrate = round((victorias / total_partidas * 100), 1) if total_partidas > 0 else 0
    
    # Obtener comentarios y tiers personalizados del usuario
    comentarios_db = list(comentarios_tier_usuarios_collection.find({"usuario": user_obj.username}))
    comentarios_map = {str(c['campeon_id']): c for c in comentarios_db}
    
    # Construir la tier list personalizada del usuario
    tier_list_usuario = []
    for p in personajes_db:
        p_custom = comentarios_map.get(p['id'], {})
        tier_list_usuario.append({
            'id': p['id'],
            'nombre': p['nombre'],
            'icon': p.get('icon', ''),
            'roles': p.get('roles', []),
            'tier_global': p.get('tier', 'B'),
            'tier_personal': p_custom.get('tier'),
            'comentario_personal': p_custom.get('comentario', ''),
            'tier_efectivo': p_custom.get('tier') or p.get('tier', 'B')
        })
        
    # Ordenar tier list por tier efectivo y luego por nombre
    tier_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
    tier_list_usuario = sorted(tier_list_usuario, key=lambda x: (
        tier_order.get(x['tier_efectivo'], 99),
        x['nombre']
    ))
    
    # Si es administrador, obtener historial de cambios de tier global que realizó
    historial_cambios = []
    if user_obj.is_staff:
        pipeline_cambios = [
            {"$match": {"historial_tier.realizado_por": user_obj.username}},
            {"$unwind": "$historial_tier"},
            {"$match": {"historial_tier.realizado_por": user_obj.username}},
            {"$project": {
                "_id": 1,
                "nombre": 1,
                "icon": 1,
                "tier_actual": "$tier",
                "tier_anterior": "$historial_tier.tier_anterior",
                "tier_nuevo": "$historial_tier.tier_nuevo",
                "motivo": "$historial_tier.motivo",
                "fecha": "$historial_tier.fecha",
            }},
            {"$sort": {"fecha": -1}}
        ]
        historial_cambios = list(personajes_collection.aggregate(pipeline_cambios))
        for h in historial_cambios:
            h['campeon_id'] = str(h['_id'])

    # Obtener campeones favoritos del usuario
    favoritos_docs = list(favoritos_collection.find({"usuario": user_obj.username}).sort("fecha", -1))
    favoritos_ids = [f['campeon_id'] for f in favoritos_docs]
    favoritos_campeones = []
    if favoritos_ids:
        favs_db = list(personajes_collection.find({"_id": {"$in": favoritos_ids}}))
        fav_map = {str(f['_id']): f for f in favs_db}
        for fav_doc in favoritos_docs:
            champ = fav_map.get(str(fav_doc['campeon_id']))
            if champ:
                favoritos_campeones.append({
                    'id': str(champ['_id']),
                    'nombre': champ['nombre'],
                    'icon': champ.get('icon', ''),
                    'tier': champ.get('tier', 'B'),
                    'roles': champ.get('roles', []),
                    'fecha_favorito': fav_doc.get('fecha', ''),
                })

    return render(request, 'perfil_usuario.html', {
        'perfil_user': user_obj,
        'partidas': partidas,
        'total_partidas': total_partidas,
        'victorias': victorias,
        'derrotas': derrotas,
        'winrate': winrate,
        'tier_list_usuario': tier_list_usuario,
        'historial_cambios': historial_cambios,
        'es_propio': (request.user.username == user_obj.username),
        'favoritos_campeones': favoritos_campeones,
    })


@login_required
def guardar_tier_comentario(request, champ_id):
    """
    Guarda o actualiza el tier y comentario personalizado de un usuario para un campeón.
    """
    if request.method == 'POST':
        tier = request.POST.get('tier', '').strip().upper()
        comentario = request.POST.get('comentario', '').strip()
        
        if tier not in ['S', 'A', 'B', 'C', 'D', '']:
            messages.error(request, "Tier no válido. Usa S, A, B, C, D o déjalo vacío.")
            return redirect('perfil_usuario', username=request.user.username)
            
        try:
            champ_obj_id = ObjectId(champ_id)
            campeon = personajes_collection.find_one({"_id": champ_obj_id})
            if not campeon:
                messages.error(request, "Campeón no encontrado.")
                return redirect('perfil_usuario', username=request.user.username)
                
            filtro = {"usuario": request.user.username, "campeon_id": champ_obj_id}
            
            # Si tanto tier como comentario se dejan vacíos, se elimina la preferencia personalizada
            if not tier and not comentario:
                comentarios_tier_usuarios_collection.delete_one(filtro)
                messages.success(request, f"Se eliminaron tus preferencias personalizadas para {campeon['nombre']}.")
            else:
                update_data = {
                    "usuario": request.user.username,
                    "campeon_id": champ_obj_id,
                    "tier": tier if tier else None,
                    "comentario": comentario,
                    "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }
                comentarios_tier_usuarios_collection.update_one(
                    filtro,
                    {"$set": update_data},
                    upsert=True
                )
                messages.success(request, f"Preferencias actualizadas para {campeon['nombre']}.")
        except Exception as e:
            messages.error(request, f"Error al guardar tus preferencias: {e}")
            
    return redirect('perfil_usuario', username=request.user.username)


@login_required
def editar_partida(request, partida_id):
    """
    Permite modificar una partida manual registrada por el usuario actual o por un administrador.
    """
    try:
        partida_obj_id = ObjectId(partida_id)
        partida = partidas_analizadas_collection.find_one({"_id": partida_obj_id})
        
        if not partida:
            messages.error(request, "Partida no encontrada.")
            return redirect('reporte_partidas_analizadas')
            
        # Validar permisos (propietario o administrador)
        if partida.get('registrado_por') != request.user.username and not request.user.is_staff:
            messages.error(request, "No tienes permiso para editar esta partida.")
            return redirect('reporte_partidas_analizadas')
            
        campeon = personajes_collection.find_one({"_id": partida['campeon_id']})
        
        if request.method == 'POST':
            resultado = request.POST.get('resultado', '').strip()
            duracion = request.POST.get('duracion', '').strip()
            kills = request.POST.get('kills', '0').strip()
            deaths = request.POST.get('deaths', '0').strip()
            assists = request.POST.get('assists', '0').strip()
            carril = request.POST.get('carril', '').strip()
            notas = request.POST.get('notas', '').strip()

            if resultado not in ['Victoria', 'Derrota']:
                messages.error(request, "El resultado debe ser 'Victoria' o 'Derrota'.")
                return redirect('editar_partida', partida_id=partida_id)

            try:
                duracion_int = int(duracion)
                kills_int = int(kills)
                deaths_int = int(deaths)
                assists_int = int(assists)
            except ValueError:
                messages.error(request, "Los valores numéricos no son válidos.")
                return redirect('editar_partida', partida_id=partida_id)
                
            update_data = {
                "resultado": resultado,
                "duracion_min": duracion_int,
                "kills": kills_int,
                "deaths": deaths_int,
                "assists": assists_int,
                "carril": carril,
                "notas": notas,
            }
            
            partidas_analizadas_collection.update_one(
                {"_id": partida_obj_id},
                {"$set": update_data}
            )
            messages.success(request, "Partida actualizada exitosamente.")
            return redirect('perfil_usuario', username=partida.get('registrado_por'))
            
        return render(request, 'editar_partida.html', {
            'partida': partida,
            'partida_id': partida_id,
            'campeon': campeon
        })
    except Exception as e:
        messages.error(request, f"Error al editar partida: {e}")
        return redirect('reporte_partidas_analizadas')


@login_required
def eliminar_partida(request, partida_id):
    """
    Permite eliminar una partida manual registrada por el usuario actual o por un administrador.
    """
    try:
        partida_obj_id = ObjectId(partida_id)
        partida = partidas_analizadas_collection.find_one({"_id": partida_obj_id})
        
        if not partida:
            messages.error(request, "Partida no encontrada.")
            return redirect('reporte_partidas_analizadas')
            
        # Validar permisos (propietario o administrador)
        if partida.get('registrado_por') != request.user.username and not request.user.is_staff:
            messages.error(request, "No tienes permiso para eliminar esta partida.")
            return redirect('reporte_partidas_analizadas')
            
        registrado_por = partida.get('registrado_por')
        partidas_analizadas_collection.delete_one({"_id": partida_obj_id})
        messages.success(request, "Partida eliminada exitosamente.")
        return redirect('perfil_usuario', username=registrado_por)
    except Exception as e:
        messages.error(request, f"Error al eliminar la partida: {e}")
        return redirect('reporte_partidas_analizadas')


# ============================================================
# NUEVAS INTERACCIONES PARA USUARIOS NORMALES
# ============================================================

@login_required
def votar_tier(request, pk):
    """
    Permite a cualquier usuario logueado votar el tier de un campeón (S/A/B/C/D).
    Un usuario solo puede tener un voto activo por campeón (upsert).
    """
    if request.method == 'POST':
        tier = request.POST.get('tier', '').strip().upper()
        if tier not in ['S', 'A', 'B', 'C', 'D']:
            messages.error(request, "Tier de voto no válido.")
            return redirect('campeon_detalle', pk=pk)
        try:
            obj_id = ObjectId(pk)
            votos_tier_collection.update_one(
                {"campeon_id": obj_id, "usuario": request.user.username},
                {"$set": {
                    "campeon_id": obj_id,
                    "usuario": request.user.username,
                    "tier": tier,
                    "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                }},
                upsert=True
            )
            messages.success(request, f"¡Votaste Tier {tier} para este campeón!")
        except Exception as e:
            messages.error(request, f"Error al registrar voto: {e}")
    return redirect('campeon_detalle', pk=pk)


@login_required
def comentar_campeon(request, pk):
    """
    Permite a cualquier usuario logueado dejar un comentario público
    en la página de detalle del campeón. Visible para todos.
    """
    if request.method == 'POST':
        texto = request.POST.get('texto', '').strip()
        if not texto:
            messages.error(request, "El comentario no puede estar vacío.")
            return redirect('campeon_detalle', pk=pk)
        if len(texto) > 500:
            messages.error(request, "El comentario no puede superar los 500 caracteres.")
            return redirect('campeon_detalle', pk=pk)
        try:
            obj_id = ObjectId(pk)
            comentarios_publicos_collection.insert_one({
                "campeon_id": obj_id,
                "usuario": request.user.username,
                "texto": texto,
                "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })
            messages.success(request, "¡Comentario publicado exitosamente!")
        except Exception as e:
            messages.error(request, f"Error al publicar comentario: {e}")
    return redirect('campeon_detalle', pk=pk)


@login_required
def eliminar_comentario_publico(request, comentario_id):
    """
    Permite eliminar un comentario público propio (o de cualquiera si es admin).
    """
    try:
        c_obj_id = ObjectId(comentario_id)
        comentario = comentarios_publicos_collection.find_one({"_id": c_obj_id})
        if not comentario:
            messages.error(request, "Comentario no encontrado.")
            return redirect('campeones')
        # Solo el autor o un admin puede eliminar
        if comentario.get('usuario') != request.user.username and not request.user.is_staff:
            messages.error(request, "No tienes permiso para eliminar este comentario.")
            return redirect('campeon_detalle', pk=str(comentario['campeon_id']))
        campeon_pk = str(comentario['campeon_id'])
        comentarios_publicos_collection.delete_one({"_id": c_obj_id})
        messages.success(request, "Comentario eliminado.")
        return redirect('campeon_detalle', pk=campeon_pk)
    except Exception as e:
        messages.error(request, f"Error al eliminar comentario: {e}")
        return redirect('campeones')


@login_required
def toggle_favorito(request, pk):
    """
    Marca o desmarca un campeón como favorito para el usuario actual.
    Si ya es favorito, lo quita. Si no lo es, lo agrega.
    """
    try:
        obj_id = ObjectId(pk)
        filtro = {"campeon_id": obj_id, "usuario": request.user.username}
        existente = favoritos_collection.find_one(filtro)
        if existente:
            favoritos_collection.delete_one(filtro)
            messages.success(request, "Campeón eliminado de tus favoritos.")
        else:
            favoritos_collection.insert_one({
                "campeon_id": obj_id,
                "usuario": request.user.username,
                "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            })
            messages.success(request, "¡Campeón agregado a tus favoritos!")
    except Exception as e:
        messages.error(request, f"Error al actualizar favoritos: {e}")
    return redirect('campeon_detalle', pk=pk)


def registro(request):
    """
    Permite registrar un nuevo usuario.
    Si el usuario logueado es admin, le permite marcar si el nuevo usuario será admin (staff).
    Si es un usuario público/anonimo, lo registra como normal y le inicia la sesión.
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            
            # Asignación de roles
            es_admin_creador = request.user.is_authenticated and request.user.is_staff
            hacer_staff = False
            if es_admin_creador and request.POST.get('is_staff') == 'on':
                hacer_staff = True
            
            if hacer_staff:
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_staff = False
                user.is_superuser = False
                
            user.save()
            
            if es_admin_creador:
                messages.success(request, f"Usuario '{user.username}' creado exitosamente.")
                return redirect('registro')
            else:
                messages.success(request, "¡Registro completado con éxito! Bienvenido a DataSoft.")
                login(request, user)
                return redirect('inicio')
    else:
        form = UserCreationForm()
        
    return render(request, 'registration/registro.html', {
        'form': form
    })
