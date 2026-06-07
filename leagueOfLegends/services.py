import requests
import os
import json
from django.conf import settings

_GLOBAL_VERSION_CACHE = None

def get_latest_version_cached():
    global _GLOBAL_VERSION_CACHE
    if _GLOBAL_VERSION_CACHE:
        return _GLOBAL_VERSION_CACHE
    try:
        version_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        _GLOBAL_VERSION_CACHE = requests.get(version_url, timeout=3).json()[0]
        return _GLOBAL_VERSION_CACHE
    except:
        return "14.10.1"

def load_probuilds():
    try:
        json_path = os.path.join(settings.BASE_DIR, 'leagueOfLegends', 'static', 'data', 'probuilds.json')
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading probuilds.json: {e}")
    return {}

def fetch_champion_data(champion_name):
    """
    Fetches champion data from Riot Games Data Dragon.
    """
    try:
        # 1. Get latest version
        version = get_latest_version_cached()

        # 2. Find the champion ID from the full list
        # We need this because the user might type "Jarvan IV" but the ID is "JarvanIV"
        list_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
        champions_list = requests.get(list_url).json()['data']
        
        champion_id = None
        search_name = champion_name.replace(" ", "").replace("'", "").lower()
        
        for cid, data in champions_list.items():
            if data['name'].lower() == champion_name.lower() or cid.lower() == search_name:
                champion_id = cid
                break
        
        if not champion_id:
            return None

        # 3. Get detailed data
        detail_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{champion_id}.json"
        detail_data = requests.get(detail_url).json()['data'][champion_id]

        # 4. Format the data for our model
        # Importante: el ID para el CDN (splash) debe ser el ID interno de Riot (ej: "Aatrox")
        formatted_data = {
            "nombre": detail_data['name'],
            "roles": detail_data['tags'],
            "dificultad": str(detail_data['info']['difficulty']),
            "tipo_dano": "Melee" if detail_data['stats']['attackrange'] < 300 else "Ranged",
            "habilidades": [
                {
                    "id": s['id'],
                    "nombre": s['name'],
                    "descripcion": s['description'],
                    "imagen": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/spell/{s['image']['full']}"
                } for s in detail_data['spells']
            ],
            "estadisticas": {
                **detail_data['stats'],
                "winrate": 50.0 + (detail_data['info']['difficulty'] * 0.5) # Simular winrate basado en dificultad
            },
            "icon": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_id}.png",
            "sprite": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/sprite/{detail_data['image']['sprite']}",
            "splash": f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champion_id}_0.jpg",
            "loading": f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{champion_id}_0.jpg"
        }
        
        # Add passive to abilities
        passive = detail_data['passive']
        formatted_data['habilidades'].insert(0, {
            "id": "passive",
            "nombre": passive['name'],
            "descripcion": passive['description'],
            "imagen": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/passive/{passive['image']['full']}"
        })

        return formatted_data
    except Exception as e:
        print(f"Error fetching champion data: {e}")
        return None

_GLOBAL_RUNES_CACHE = None
def fetch_runes():
    """
    Fetches the list of all runes (Perks) from Riot.
    """
    global _GLOBAL_RUNES_CACHE
    if _GLOBAL_RUNES_CACHE:
        return _GLOBAL_RUNES_CACHE
    try:
        version = get_latest_version_cached()
        runes_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"
        _GLOBAL_RUNES_CACHE = requests.get(runes_url).json()
        return _GLOBAL_RUNES_CACHE
    except:
        return []

def get_recommended_runes(roles, name=None):
    """
    Returns a set of runes based on champion roles or static probuilds.json.
    """
    if name:
        probuilds = load_probuilds()
        champ_key = name.strip().lower()
        if champ_key in probuilds and "runas" in probuilds[champ_key]:
            return probuilds[champ_key]["runas"]

    all_runes = fetch_runes()
    if not all_runes: return []

    # Mapeo básico de rol a rama de runas
    role_to_style = {
        'Tank': 'Resolve',
        'Mage': 'Sorcery',
        'Assassin': 'Domination',
        'Fighter': 'Precision',
        'Marksman': 'Precision',
        'Support': 'Inspiration'
    }

    primary_role = roles[0] if roles else 'Fighter'
    style_key = role_to_style.get(primary_role, 'Precision')
    
    selected_style = next((s for s in all_runes if s['key'] == style_key), all_runes[0])
    
    recommended = []
    # Tomar la runa clave y 3 runas menores
    for slot in selected_style['slots']:
        rune = slot['runes'][0] # Tomamos la primera de cada fila por simplicidad
        recommended.append({
            "nombre": rune['name'],
            "icono": f"https://ddragon.leagueoflegends.com/cdn/img/{rune['icon']}"
        })
    
    return recommended

_GLOBAL_ITEMS_CACHE = None
def fetch_items():
    global _GLOBAL_ITEMS_CACHE
    if _GLOBAL_ITEMS_CACHE:
        return _GLOBAL_ITEMS_CACHE
    try:
        version = get_latest_version_cached()
        items_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
        _GLOBAL_ITEMS_CACHE = requests.get(items_url).json()
        return _GLOBAL_ITEMS_CACHE
    except:
        return {}

def get_recommended_build(roles, name=None):
    if name:
        probuilds = load_probuilds()
        champ_key = name.strip().lower()
        if champ_key in probuilds and "builds" in probuilds[champ_key]:
            return probuilds[champ_key]["builds"]

    items_data = fetch_items().get('data', {})
    if not items_data: return []

    # Mapeo de items clave por rol (IDs actualizados 14.10)
    role_to_items = {
        'Tank': ['3068', '3075', '3110', '3001', '3065', '3193'], 
        'Mage': ['3089', '3157', '3165', '4633', '3135', '3020'], 
        'Assassin': ['3142', '3147', '3814', '6692', '3158', '3117'],
        'Fighter': ['3071', '3053', '3161', '6333', '3047', '3074'], 
        'Marksman': ['3031', '3085', '3046', '3036', '3006', '3094'], 
        'Support': ['3107', '3190', '3504', '3174', '3011', '3117'] 
    }

    primary_role = roles[0] if roles else 'Fighter'
    item_ids = role_to_items.get(primary_role, ['3071', '3053'])
    
    version = get_latest_version_cached()

    build = []
    for iid in item_ids:
        item = items_data.get(iid)
        if item:
            build.append({
                "nombre": item['name'],
                "icono": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{iid}.png"
            })
    return build

def get_matchup_details(champion_names, is_favorable=True, current_champion_name=None):
    """
    Returns detailed matchup profiles containing specific winrates, roles, and strategy tips.
    """
    version = get_latest_version_cached()
    
    # Hand-crafted tips for key champions to show ultra-premium details
    key_matchups = {
        "aatrox": {
            "fiora": "Su W (Réplica) puede aturdirte si bloquea tu tercera Q. Compra Cortacuras temprano y juega alrededor de su pasiva.",
            "vayne": "Muy difícil. Guarda tu E para cuando ella use su Q o para esquivar su condena. Cuidado con su daño verdadero.",
            "garen": "Evita tradeos extremadamente largos por su regeneración pasiva. Castígalo con tu Q1 y Q2 cuando intente farmear.",
            "yasuo": "Castiga su fase de líneas con tu rango de la Q. Recuerda que su Muro de Viento no bloquea el impacto de tu Espada de los Oscuros.",
            "yone": "Pelea cuando su E (Alma desatada) esté en enfriamiento. Intenta predecir dónde regresará su cuerpo para acertar tu combo.",
            "irelia": "Espera a que gaste sus acumulaciones de la pasiva. Mantén la distancia cuando tenga minions con poca vida cerca."
        },
        "yasuo": {
            "aatrox": "Esquiva sus zonas de impacto de la Q deslizándote con tu E a través de sus súbditos. Tu muro no bloquea sus golpes directos.",
            "fiora": "Un duelo de pura habilidad. Usa tu pasiva de escudo para absorber su daño y guarda tu E para esquivar sus estocadas.",
            "lux": "Matchup muy favorable. Usa tu Muro de Viento (W) para bloquear su Q (Prisión de Luz) y su E, anulando su combo.",
            "ahri": "Bloquea su Seducción (E) con tu muro de viento. Si lo logras, tienes la ventaja completa para ganarle el tradeo."
        }
    }
    
    current_champ_lower = current_champion_name.strip().lower() if current_champion_name else ""
    
    details = []
    for name in champion_names:
        name_clean = name.strip()
        name_lower = name_clean.lower()
        cid = name_clean.replace(" ", "").replace("'", "")
        
        # Winrate realista basado en si es favorable o no
        h = hash(name_clean + str(current_champ_lower))
        if is_favorable:
            wr = round(51.2 + (abs(h) % 48) * 0.1, 1) # 51.2% - 56.0%
        else:
            wr = round(43.5 + (abs(h) % 45) * 0.1, 1) # 43.5% - 48.0%
            
        # Consejos estratégicos dinámicos y variados para evitar la repetición
        consejo = "Aprovecha las ventanas de enfriamiento de sus habilidades principales e inicia intercambios cortos y rápidos."
        if current_champ_lower in key_matchups and name_lower in key_matchups[current_champ_lower]:
            consejo = key_matchups[current_champ_lower][name_lower]
        elif name_lower in key_matchups and current_champ_lower in key_matchups[name_lower]:
            consejo = f"Ten cuidado. {key_matchups[name_lower][current_champ_lower]}"
        else:
            h_advice = hash(name_clean + str(current_champ_lower))
            favorable_advices = [
                f"Abusa de tu ventaja de rango o de tus enfriamientos más cortos. Castiga a {name_clean} cada vez que intente dar el último golpe a los súbditos.",
                f"Tus intercambios cortos son muy superiores. Intenta desgastar a {name_clean} y retrocede antes de que pueda responder de forma prolongada.",
                f"Controla la oleada cerca de tu torre. Esto obligará a {name_clean} a exponerse para farmear, abriendo ventanas de gankeo muy claras.",
                f"Guarda tu habilidad de movilidad o control para esquivar o interrumpir la iniciación de {name_clean}. Tienes la ventaja en peleas completas.",
                f"Consigue prioridad de línea temprano. {name_clean} tiene problemas para limpiar oleadas bajo torre, lo que te permite rotar libremente."
            ]
            desfavorable_advices = [
                f"Evita intercambios largos con {name_clean}. Prioriza farmear de forma segura bajo torre y solicita asistencia de tu jungla para castigar su presión.",
                f"Compra resistencia temprana (armadura o resistencia mágica) para mitigar el daño explosivo de {name_clean}. No busques el 1v1 sin ventaja.",
                f"Mantén excelente visión en los arbustos y el río. {name_clean} buscará emboscarte desde la niebla de guerra para iniciar con ventaja.",
                f"Juega alrededor de los enfriamientos de {name_clean}. Si gasta su habilidad principal en la oleada de súbditos, castígalo de inmediato.",
                f"No te expongas a su hostigamiento innecesario. Es preferible perder algunos súbditos que darle una eliminación fácil a {name_clean}."
            ]
            if is_favorable:
                consejo = favorable_advices[abs(h_advice) % len(favorable_advices)]
            else:
                consejo = desfavorable_advices[abs(h_advice) % len(desfavorable_advices)]
                
        details.append({
            "nombre": name_clean,
            "icono": f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{cid}.png",
            "wr": wr,
            "consejo": consejo
        })
    return details

# --- SISTEMA DE ENRIQUECIMIENTO Y MATCHUPS DINÁMICOS POR ROLES Y CARRILES ---

ROLE_MATCHUPS = {
    'Assassin': {
        'Mage': 3.0,
        'Marksman': 4.0,
        'Fighter': -2.0,
        'Tank': -4.0,
        'Support': 2.0,
    },
    'Tank': {
        'Assassin': 4.0,
        'Marksman': -3.0,
        'Fighter': -4.0,
        'Mage': 1.0,
        'Support': 2.0,
    },
    'Fighter': {
        'Tank': 4.0,
        'Assassin': 2.0,
        'Mage': -3.0,
        'Marksman': -2.0,
        'Support': 1.0,
    },
    'Mage': {
        'Fighter': 3.0,
        'Assassin': -3.0,
        'Tank': -1.0,
        'Marksman': 2.0,
        'Support': 1.0,
    },
    'Marksman': {
        'Tank': 3.0,
        'Fighter': 2.0,
        'Assassin': -4.0,
        'Mage': -2.0,
        'Support': 1.0,
    },
    'Support': {
        'Assassin': -2.0,
        'Tank': -2.0,
        'Fighter': -1.0,
        'Mage': -1.0,
        'Marksman': -1.0,
    }
}

def get_lanes_for_champion(roles):
    if not roles:
        return ['top']
    return [r.lower() for r in roles]

def get_riot_classes_for_champion(champion):
    if not champion:
        return ['Fighter']
    if 'riot_roles' in champion and champion['riot_roles']:
        return champion['riot_roles']
    name = champion.get('nombre', '').lower().strip()
    name_to_tags = {
        'aatrox': ['Fighter'],
        'garen': ['Fighter', 'Tank'],
        'rengar': ['Assassin', 'Fighter'],
        'orianna': ['Mage'],
    }
    if name in name_to_tags:
        return name_to_tags[name]
    # Si no está en estático, intentar mapear desde roles existentes
    roles = champion.get('roles', [])
    riot_classes = ['Fighter', 'Mage', 'Marksman', 'Assassin', 'Tank', 'Support']
    tags = [r for r in roles if r in riot_classes]
    if tags:
        return tags
    # Fallback por línea
    lanes = [r.lower() for r in roles]
    if 'support' in lanes:
        return ['Support']
    if 'adc' in lanes:
        return ['Marksman']
    if 'jungle' in lanes:
        return ['Assassin']
    if 'mid' in lanes:
        return ['Mage']
    return ['Fighter']

def get_consistent_winrate_for_tier(tier, name):
    tier_clean = str(tier).strip().upper()
    
    # Mapeo estricto del Tier a tasas de victoria entre 44% y 56%
    if tier_clean in ['S+', 'S']:
        low, high = 54.5, 56.0
    elif tier_clean in ['S-', 'A+']:
        low, high = 53.0, 54.4
    elif tier_clean in ['A', 'A-']:
        low, high = 51.5, 52.9
    elif tier_clean in ['B+', 'B']:
        low, high = 49.5, 51.4
    elif tier_clean in ['B-', 'C+']:
        low, high = 48.5, 49.4
    elif tier_clean in ['C', 'C-']:
        low, high = 46.5, 48.4
    elif tier_clean in ['D']:
        low, high = 45.0, 46.4
    else: # F o cualquier otro
        low, high = 44.0, 44.9
        
    # Winrate determinista usando hash del nombre del campeón
    h = hash(name)
    spread = high - low
    wr = low + (abs(h) % 1000) / 1000 * spread
    return round(wr, 2)

def get_custom_advice(roles_a, roles_b):
    primary_a = roles_a[0] if roles_a else 'Fighter'
    primary_b = roles_b[0] if roles_b else 'Fighter'
    
    combos = {
        ('Assassin', 'Mage'): "Esquiva su habilidad de control de masas clave y castígalo con tu ráfaga de daño rápido.",
        ('Assassin', 'Marksman'): "Usa las malezas y la niebla de guerra para emboscarlo y eliminarlo antes de que pueda reposicionarse.",
        ('Tank', 'Assassin'): "Usa tu control de masas para detener su iniciación y proteger a tus carries principales.",
        ('Fighter', 'Tank'): "Realiza intercambios extendidos. Tu daño sostenido y penetración superarán su mitigación de daño.",
        ('Mage', 'Fighter'): "Mantén la distancia usando tu rango y ralentizaciones. No permitas que acorte la distancia sin recibir daño previo.",
        ('Marksman', 'Tank'): "Mantén una posición segura detrás de tu línea frontal y aprovecha tu daño sostenido para derribarlo en peleas extendidas.",
        ('Support', 'Assassin'): "Conserva tus curas, escudos o control de masas específicamente para cuando intente saltar sobre tu tirador.",
    }
    return combos.get((primary_a, primary_b), "Aprovecha las ventanas de enfriamiento de sus habilidades principales para ganar los intercambios.")

def enrich_champion_data(p, all_champions=None):
    # Asegurar ID como string
    if '_id' in p:
        p['id'] = str(p['_id'])
        
    # Asegurar recursos básicos
    p['splash'] = p.get('splash') or 'https://ddragon.leagueoflegends.com/cdn/img/champion/splash/Aatrox_0.jpg'
    p['icon'] = p.get('icon') or 'https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/Aatrox.png'
    p['roles'] = p.get('roles') or ['Fighter']
    p['tier'] = p.get('tier') or 'B'
    
    # 2. Winrate consistente basado en Tier del CRUD
    wr = get_consistent_winrate_for_tier(p['tier'], p['nombre'])
    if not isinstance(p.get('estadisticas'), dict):
        p['estadisticas'] = {}
    p['estadisticas']['winrate'] = wr
    p['winrate'] = wr
    
    # 3. Métricas de Pickrate y Banrate deterministas
    h = hash(p['nombre'])
    p['pickrate'] = round(1.5 + (abs(h) % 135) * 0.1, 1)
    p['banrate'] = round(0.5 + (abs(h) % 345) * 0.1, 1)
    
    # 4. Objetos core y runas
    riot_tags = get_riot_classes_for_champion(p)
    p['items_recomendados'] = get_recommended_build(riot_tags, p['nombre'])[:3]
    
    # Forzar regeneración dinámica para ignorar datos corruptos en la BD
    p['builds'] = get_recommended_build(riot_tags, p['nombre'])
    p['runas'] = get_recommended_runes(riot_tags, p['nombre'])
        
    # 5. Matchups dinámicos
    if all_champions is None:
        from dataSoft.mongodb.mongo import personajes_collection
        if personajes_collection is not None:
            all_champions = list(personajes_collection.find())
        else:
            all_champions = []
            
    lanes_a = get_lanes_for_champion(p['roles'])
    opponents = []
    
    # Obtener versión más reciente para las imágenes
    version = get_latest_version_cached()
        
    for opp in all_champions:
        opp_name = opp.get('nombre')
        if not opp_name or opp_name.lower().strip() == p['nombre'].lower().strip():
            continue
            
        lanes_b = get_lanes_for_champion(opp.get('roles', []))
        # Verificar si comparten al menos un carril
        shared_lanes = set(lanes_a) & set(lanes_b)
        if shared_lanes:
            roles_a = get_riot_classes_for_champion(p)
            roles_b = get_riot_classes_for_champion(opp)
            
            # Cálculo de ventaja según la matriz de roles
            total_score = 0
            count = 0
            for r_a in roles_a:
                for r_b in roles_b:
                    total_score += ROLE_MATCHUPS.get(r_a, {}).get(r_b, 0.0)
                    count += 1
            score = total_score / count if count > 0 else 0.0
            
            # Variación determinista según los nombres
            salt = (hash(p['nombre'] + opp_name) % 11 - 5) * 0.1
            opp_wr = 50.0 + score * 1.5 + salt
            opp_wr = max(40.0, min(60.0, round(opp_wr, 2)))
            
            # Consejos y estrategias
            key_matchups = {
                "aatrox": {
                    "fiora": "Su W (Réplica) puede aturdirte si bloquea tu tercera Q. Compra Cortacuras temprano y juega alrededor de su pasiva.",
                    "vayne": "Muy difícil. Guarda tu E para cuando ella use su Q o para esquivar su condena. Cuidado con su daño verdadero.",
                    "garen": "Evita tradeos extremadamente largos por su regeneración pasiva. Castígalo con tu Q1 y Q2 cuando intente farmear.",
                    "yasuo": "Castiga su fase de líneas con tu rango de la Q. Recuerda que su Muro de Viento no bloquea el impacto de tu Espada de los Oscuros.",
                    "yone": "Pelea cuando su E (Alma desatada) esté en enfriamiento. Intenta predecir dónde regresará su cuerpo para acertar tu combo.",
                    "irelia": "Espera a que gaste sus acumulaciones de la pasiva. Mantén la distancia cuando tenga minions con poca vida cerca."
                },
                "yasuo": {
                    "aatrox": "Esquiva sus zonas de impacto de la Q deslizándote con tu E a través de sus súbditos. Tu muro no bloquea sus golpes directos.",
                    "fiora": "Un duelo de pura habilidad. Usa tu pasiva de escudo para absorber su daño y guarda tu E para esquivar sus estocadas.",
                    "lux": "Matchup muy favorable. Usa tu Muro de Viento (W) para bloquear su Q (Prisión de Luz) y su E, anulando su combo.",
                    "ahri": "Bloquea su Seducción (E) con tu muro de viento. Si lo logras, tienes la ventaja completa para ganarle el tradeo."
                }
            }
            
            p_lower = p['nombre'].lower().strip()
            opp_lower = opp_name.lower().strip()
            consejo = None
            if p_lower in key_matchups and opp_lower in key_matchups[p_lower]:
                consejo = key_matchups[p_lower][opp_lower]
            elif opp_lower in key_matchups and p_lower in key_matchups[opp_lower]:
                consejo = f"Ten cuidado. {key_matchups[opp_lower][p_lower]}"
            else:
                consejo = get_custom_advice(roles_a, roles_b)
                
            opp_cid = opp_name.replace(" ", "").replace("'", "")
            opponents.append({
                "nombre": opp_name,
                "icono": opp.get('icon') or f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{opp_cid}.png",
                "wr": opp_wr,
                "consejo": consejo
            })
            
    # Ordenar oponentes por winrate descendente
    opponents_sorted = sorted(opponents, key=lambda x: x['wr'], reverse=True)
    
    # Clasificar en favorables y desfavorables
    favorables = [o for o in opponents_sorted if o['wr'] > 50.0][:4]
    desfavorables = [o for o in reversed(opponents_sorted) if o['wr'] <= 50.0][:4]
    
    p['matchup_details'] = {
        "favorables": favorables,
        "desfavorables": desfavorables
    }
    p['lane_matchups'] = opponents_sorted
    
    return p

