import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from django.conf import settings

class MongoDBConnection:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            uri = getattr(settings, 'MONGODB_URI', "mongodb://localhost:27017/")
            try:
                cls._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                cls._client.admin.command('ping')
                print("Conexion a MongoDB exitosa")
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                print(f"Error al conectar a MongoDB: {e}")
                cls._client = None
        return cls._client

    @classmethod
    def get_db(cls):
        client = cls.get_client()
        if client:
            db_name = getattr(settings, 'MONGODB_NAME', "dataSoft_db")
            return client[db_name]
        return None

db = MongoDBConnection.get_db()
if db is not None:
    personajes_collection = db["personajes"]
    partidas_analizadas_collection = db["partidas_analizadas"]
    comentarios_tier_usuarios_collection = db["comentarios_tier_usuarios"]
    # Nuevas colecciones para interacción de usuarios normales
    votos_tier_collection = db["votos_tier"]              # Votos de tier por usuario (S/A/B/C/D)
    comentarios_publicos_collection = db["comentarios_publicos"]  # Comentarios públicos en detalle del campeón
    favoritos_collection = db["favoritos"]                # Favoritos de usuarios
else:
    personajes_collection = None
    partidas_analizadas_collection = None
    comentarios_tier_usuarios_collection = None
    votos_tier_collection = None
    comentarios_publicos_collection = None
    favoritos_collection = None
    print("Advertencia: colecciones no disponibles (Base de Datos desconectada)")

