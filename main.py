from fastapi import FastAPI, HTTPException, Path, Request
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from prometheus_client import Counter, Gauge, generate_latest
from fastapi.responses import Response
import yaml
import os
from typing import AsyncGenerator
import psutil  # Для мониторинга системных метрик
import uvicorn
import logging
from logging_loki import LokiHandler

# Функция для синхронизации OpenAPI-схемы в файл
def update_openapi_schema(app: FastAPI):
    openapi_schema = app.openapi()
    static_path = os.path.join(os.getcwd(), "static")
    os.makedirs(static_path, exist_ok=True)
    openapi_file_path = os.path.join(static_path, "openapi.yaml")
    with open(openapi_file_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, allow_unicode=True)
    print(f"OpenAPI схема сохранена в файл {openapi_file_path}")

# Функция lifespan для генерации схемы и мониторинга системных метрик
async def lifespan(app: FastAPI) -> AsyncGenerator:
    import asyncio

    async def monitor_system_metrics():
        while True:
            cpu_usage.set(psutil.cpu_percent(interval=1))
            # Проверка на доступность температуры (не на всех системах доступно)
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures().get("coretemp", [])
                if temps:
                    cpu_temp.set(max(temp.current for temp in temps))
            memory_usage.set(psutil.virtual_memory().percent)
            await asyncio.sleep(5)

    # Обновляем OpenAPI-схему и запускаем мониторинг системных метрик
    update_openapi_schema(app)
    asyncio.create_task(monitor_system_metrics())

    yield

LOKI_URL = "http://loki:3100/loki/api/v1/push"
handler = LokiHandler(
    url=LOKI_URL,
    tags={"application": __name__},
    version="1"
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),  # Установка кодировки
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Ваше приложение FastAPI
app = FastAPI(
    title="Музыкальный каталог API",
    description="API музыкального каталога с метриками",
    version="3.0.1",
    lifespan=lifespan
)

# Метрики для HTTP-запросов
http_total_requests = Counter("http_total_requests_total", "Общее количество HTTP запросов", ["method", "http_status", "endpoint"])

# Метрики для системных ресурсов
cpu_usage = Gauge("cpu_usage", "Использование CPU в процентах")
cpu_temp = Gauge("cpu_temp", "Температура CPU в градусах Цельсия")
memory_usage = Gauge("memory_usage", "Использование памяти в процентах")

# Middleware для отслеживания методов HTTP-запросов
@app.middleware("http")
async def add_metrics(request: Request, call_next):
    response = await call_next(request)

    http_total_requests.labels(
        method=request.method,
        http_status=str(response.status_code),
        endpoint=request.url.path
    ).inc()

    # Логирование
    logger.info(f"Request {request.method} {request.url.path} completed with status {response.status_code}")

    return response

# Прочие метрики
artists_created_total = Counter("artists_created_total", "Общее количество созданных исполнителей")
albums_created_total = Counter("albums_created_total", "Общее количество созданных альбомов")
tracks_created_total = Counter("tracks_created_total", "Общее количество созданных треков")

# Временные "базы данных"
artists_db = []
albums_db = []
tracks_db = []

# Модели данных
class Track(BaseModel):
    id: int
    title: str
    duration: str
    album_id: int

class Album(BaseModel):
    id: int
    title: str
    releaseDate: date
    artist_id: int
    tracks: Optional[List[Track]] = []

class Artist(BaseModel):
    id: int
    name: str
    genre: str
    albums: Optional[List[Album]] = []

# Эндпоинт для сбора метрик
@app.get("/metrics")
def get_metrics():
    return Response(generate_latest(), media_type="text/plain")

# Эндпоинты для исполнителей
@app.post("/artist", response_model=Artist, status_code=201, tags=["artist"])
def add_artist(artist: Artist):
    try:
        if any(a.id == artist.id for a in artists_db):
            logger.error(f"Attempt to create duplicate artist with ID {artist.id}.")
            raise HTTPException(status_code=400, detail="Исполнитель с таким ID уже существует.")
        artists_db.append(artist)
        artists_created_total.inc()
        update_openapi_schema(app)
        logger.info(f"Artist {artist.name} with ID {artist.id} created.")
        return artist
    except HTTPException as e:
        logger.error(f"Error adding artist: {e.detail}. Input: {artist.dict()}")
        raise e

@app.get("/artist", response_model=List[Artist], tags=["artist"])
def get_artists():
    logger.info("Fetching all artists.")
    return artists_db

@app.get("/artist/{artistId}", response_model=Artist, tags=["artist"])
def get_artist_by_id(artistId: int):
    try:
        artist = next((a for a in artists_db if a.id == artistId), None)
        if not artist:
            logger.error(f"Artist with ID {artistId} not found.")
            raise HTTPException(status_code=404, detail="Исполнитель не найден")
        logger.info(f"Artist with ID {artistId} fetched.")
        return artist
    except HTTPException as e:
        logger.error(f"Error fetching artist: {e.detail}. Artist ID: {artistId}")
        raise e

# Эндпоинты для альбомов
@app.post("/album", response_model=Album, status_code=201, tags=["album"])
def add_album(album: Album):
    try:
        artist = next((a for a in artists_db if a.id == album.artist_id), None)
        if not artist:
            logger.error(f"Artist with ID {album.artist_id} not found for album {album.title}.")
            raise HTTPException(status_code=404, detail="Исполнитель не найден")
        albums_db.append(album)
        albums_created_total.inc()
        update_openapi_schema(app)
        logger.info(f"Album {album.title} created by artist {artist.name}.")
        return album
    except HTTPException as e:
        logger.error(f"Error adding album: {e.detail}. Input: {album.dict()}")
        raise e

@app.get("/album", response_model=List[Album], tags=["album"])
def get_albums():
    logger.info("Fetching all albums.")
    return albums_db

# Эндпоинты для треков
@app.post("/track", response_model=Track, status_code=201, tags=["track"])
def add_track(track: Track):
    try:
        album = next((al for al in albums_db if al.id == track.album_id), None)
        if not album:
            logger.error(f"Album with ID {track.album_id} not found for track {track.title}.")
            raise HTTPException(status_code=404, detail="Альбом не найден")
        tracks_db.append(track)
        tracks_created_total.inc()
        update_openapi_schema(app)
        logger.info(f"Track {track.title} created for album {album.title}.")
        return track
    except HTTPException as e:
        logger.error(f"Error adding track: {e.detail}. Input: {track.dict()}")
        raise e

@app.get("/track", response_model=List[Track], tags=["track"])
def get_tracks():
    logger.info("Fetching all tracks.")
    return tracks_db

# Запуск приложения
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
