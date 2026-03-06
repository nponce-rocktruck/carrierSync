"""
Configuración de conexión a MongoDB para CarrierSync API.
"""

import os
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


class MongoDBConnection:
    """Clase para manejar la conexión a MongoDB."""

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._async_client: Optional[AsyncIOMotorClient] = None
        self._database: Optional[Database] = None
        self._async_database: Optional[AsyncIOMotorDatabase] = None

    def get_connection_string(self) -> str:
        """Obtiene la cadena de conexión a MongoDB desde variables de entorno."""
        mongodb_url = os.getenv("MONGODB_URL", "").strip()
        database_name = os.getenv("MONGODB_DATABASE", "Samanta").strip()

        if not mongodb_url:
            error_msg = "MONGODB_URL no configurada. Debe establecerse como variable de entorno en Cloud Run."
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not mongodb_url.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError(f"URL de MongoDB inválida: debe comenzar con mongodb:// o mongodb+srv://")

        if mongodb_url.endswith("/"):
            connection_string = f"{mongodb_url}{database_name}"
        else:
            connection_string = f"{mongodb_url}/{database_name}"

        logger.info(f"URL de conexión MongoDB: .../{database_name}")
        return connection_string

    def connect(self) -> Database:
        """Establece conexión síncrona a MongoDB."""
        if self._database is None:
            connection_string = self.get_connection_string()
            self._client = MongoClient(
                connection_string,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=30000,
            )
            database_name = os.getenv("MONGODB_DATABASE", "Samanta")
            self._database = self._client[database_name]
            logger.info(f"Cliente MongoDB inicializado para: {database_name}")
        return self._database

    async def connect_async(self) -> AsyncIOMotorDatabase:
        """Establece conexión asíncrona a MongoDB."""
        if self._async_database is None:
            connection_string = self.get_connection_string()
            self._async_client = AsyncIOMotorClient(
                connection_string,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=30000,
            )
            database_name = os.getenv("MONGODB_DATABASE", "Samanta")
            self._async_database = self._async_client[database_name]
            logger.info(f"Cliente MongoDB (async) inicializado para: {database_name}")
        return self._async_database

    def get_collection(self, collection_name: str) -> Collection:
        """Obtiene una colección específica."""
        if self._database is None:
            self.connect()
        return self._database[collection_name]

    async def get_async_collection(self, collection_name: str):
        """Obtiene una colección de forma asíncrona."""
        if self._async_database is None:
            await self.connect_async()
        return self._async_database[collection_name]

    def close(self):
        """Cierra la conexión síncrona."""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None

    async def close_async(self):
        """Cierra la conexión asíncrona."""
        if self._async_client:
            self._async_client.close()
            self._async_client = None
            self._async_database = None


mongodb_connection = MongoDBConnection()


def get_database() -> Database:
    """Función helper para obtener la base de datos."""
    return mongodb_connection.connect()


def get_collection(collection_name: str) -> Collection:
    """Función helper para obtener una colección."""
    return mongodb_connection.get_collection(collection_name)


async def get_async_database():
    """Función helper para obtener la base de datos de forma asíncrona."""
    return await mongodb_connection.connect_async()


async def get_async_collection(collection_name: str):
    """Función helper para obtener una colección de forma asíncrona."""
    return await mongodb_connection.get_async_collection(collection_name)
