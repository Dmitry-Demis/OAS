from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import yaml
import os
from typing import AsyncGenerator
import uvicorn

# Функция для синхронизации OpenAPI-схемы в файл
def update_openapi_schema(app: FastAPI):
    # Генерация актуальной OpenAPI схемы
    openapi_schema = app.openapi()

    # Папка для хранения статических файлов
    static_path = os.path.join(os.getcwd(), "static")
    os.makedirs(static_path, exist_ok=True)  # Создаём папку "static", если её нет

    # Путь до файла для сохранения
    openapi_file_path = os.path.join(static_path, "openapi.yaml")

    # Записываем OpenAPI схему в файл YAML с кодировкой UTF-8
    with open(openapi_file_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, allow_unicode=True)

    print(f"OpenAPI схема сохранена в файл {openapi_file_path}")


# Функция lifespan для генерации схемы при запуске
async def lifespan(app: FastAPI) -> AsyncGenerator:
    update_openapi_schema(app)  # Обновление схемы при старте
    yield  # Указывает FastAPI, что жизненный цикл завершён


# Ваше приложение FastAPI
app = FastAPI(
    title="Музыкальный каталог API",
    description="API музыкального каталога",
    version="3.0.1",
    lifespan=lifespan
)

# Временные "базы данных"
artists_db = []
albums_db = []
tracks_db = []

# Модели данных
class Track(BaseModel):
    id: int
    title: str
    duration: str
    album_id: int  # Используем только ID альбома

class Album(BaseModel):
    id: int
    title: str
    releaseDate: date
    artist_id: int  # Добавлено поле для связи с исполнителем
    tracks: Optional[List[Track]] = []  # Добавлено поле для треков

class Artist(BaseModel):
    id: int
    name: str
    genre: str
    albums: Optional[List[Album]] = []


# Эндпоинты для массового добавления исполнителей, альбомов и треков
@app.post("/artists", response_model=List[Artist], status_code=201, tags=["artist"])
def add_artists(artists: List[Artist]):
    for artist in artists:
        if any(a.id == artist.id for a in artists_db):
            raise HTTPException(status_code=400, detail=f"Исполнитель с ID {artist.id} уже существует.")
        artists_db.append(artist)
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return artists


@app.post("/albums", response_model=List[Album], status_code=201, tags=["album"])
def add_albums(albums: List[Album]):
    for album in albums:
        artist = next((a for a in artists_db if a.id == album.artist_id), None)
        if not artist:
            raise HTTPException(status_code=404, detail=f"Исполнитель с ID {album.artist_id} не найден.")

        if any(al.id == album.id for al in albums_db):
            raise HTTPException(status_code=400, detail=f"Альбом с ID {album.id} уже существует.")

        albums_db.append(album)
        artist.albums.append(album)
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return albums


@app.post("/tracks", response_model=List[Track], status_code=201, tags=["track"])
def add_tracks(tracks: List[Track]):
    for track in tracks:
        album = next((al for al in albums_db if al.id == track.album_id), None)
        if not album:
            raise HTTPException(status_code=404, detail=f"Альбом с ID {track.album_id} не найден.")

        if any(t.id == track.id for t in tracks_db):
            raise HTTPException(status_code=400, detail=f"Трек с ID {track.id} уже существует.")

        tracks_db.append(track)
        album.tracks.append(track)
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return tracks


# Эндпоинты для исполнителей
@app.post("/artist", response_model=Artist, status_code=201, tags=["artist"])
def add_artist(artist: Artist):
    if any(a.id == artist.id for a in artists_db):
        raise HTTPException(status_code=400, detail="Исполнитель с таким ID уже существует.")
    artists_db.append(artist)
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return artist

@app.get("/artist", response_model=List[Artist], tags=["artist"])
def get_artists():
    return artists_db

@app.get("/artist/{artistId}", response_model=Artist, tags=["artist"])
def get_artist_by_id(artistId: int):
    artist = next((a for a in artists_db if a.id == artistId), None)
    if not artist:
        raise HTTPException(status_code=404, detail="Исполнитель не найден")
    return artist

@app.put("/artist/{artistId}", response_model=Artist, tags=["artist"])
def update_artist(artistId: int, updated_artist: Artist):
    artist = next((a for a in artists_db if a.id == artistId), None)
    if not artist:
        raise HTTPException(status_code=404, detail="Исполнитель не найден")
    artist.name = updated_artist.name
    artist.genre = updated_artist.genre
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return artist

@app.delete("/artist/{artistId}", status_code=204, tags=["artist"])
def delete_artist(artistId: int):
    global artists_db
    artist = next((a for a in artists_db if a.id == artistId), None)
    if not artist:
        raise HTTPException(status_code=404, detail="Исполнитель не найден")
    artists_db = [a for a in artists_db if a.id != artistId]
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Исполнитель удалён"}


# Эндпоинты для альбомов
@app.post("/album", response_model=Album, status_code=201, tags=["album"])
def add_album(album: Album):
    artist = next((a for a in artists_db if a.id == album.artist_id), None)
    if not artist:
        raise HTTPException(status_code=404, detail="Исполнитель не найден")

    if any(al.id == album.id for al in albums_db):
        raise HTTPException(status_code=400, detail="Альбом с таким ID уже существует.")

    albums_db.append(album)
    artist.albums.append(album)

    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return album

@app.get("/album", response_model=List[Album], tags=["album"])
def get_albums():
    return albums_db

@app.get("/album/{albumId}", response_model=Album, tags=["album"])
def get_album_by_id(albumId: int):
    album = next((al for al in albums_db if al.id == albumId), None)
    if not album:
        raise HTTPException(status_code=404, detail="Альбом не найден")
    return album

@app.put("/album/{albumId}", response_model=Album, tags=["album"])
def update_album(albumId: int, updated_album: Album):
    album = next((al for al in albums_db if al.id == albumId), None)
    if not album:
        raise HTTPException(status_code=404, detail="Альбом не найден")
    album.title = updated_album.title
    album.releaseDate = updated_album.releaseDate
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return album

@app.delete("/album/{albumId}", status_code=204, tags=["album"])
def delete_album(albumId: int):
    global albums_db
    album = next((al for al in albums_db if al.id == albumId), None)
    if not album:
        raise HTTPException(status_code=404, detail="Альбом не найден")
    albums_db = [al for al in albums_db if al.id != albumId]
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Альбом удалён"}


# Эндпоинты для треков
@app.post("/track", response_model=Track, status_code=201, tags=["track"])
def add_track(track: Track):
    album = next((al for al in albums_db if al.id == track.album_id), None)
    if not album:
        raise HTTPException(status_code=404, detail="Альбом не найден")

    if any(t.id == track.id for t in tracks_db):
        raise HTTPException(status_code=400, detail="Трек с таким ID уже существует.")

    tracks_db.append(track)
    album.tracks.append(track)

    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return track

@app.get("/track", response_model=List[Track], tags=["track"])
def get_tracks():
    return tracks_db

@app.get("/track/{trackId}", response_model=Track, tags=["track"])
def get_track_by_id(trackId: int):
    track = next((t for t in tracks_db if t.id == trackId), None)
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")
    return track

@app.put("/track/{trackId}", response_model=Track, tags=["track"])
def update_track(trackId: int, updated_track: Track):
    track = next((t for t in tracks_db if t.id == trackId), None)
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")
    track.title = updated_track.title
    track.duration = updated_track.duration
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return track

@app.delete("/track/{trackId}", status_code=204, tags=["track"])
def delete_track(trackId: int):
    global tracks_db
    track = next((t for t in tracks_db if t.id == trackId), None)
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")
    tracks_db = [t for t in tracks_db if t.id != trackId]
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Трек удалён"}

# Эндпоинты для удаления всех данных
@app.delete("/delete_all_artists", status_code=204, tags=["artist"])
def delete_all_artists():
    global artists_db
    artists_db.clear()
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Все исполнители удалены"}


@app.delete("/delete_all_albums", status_code=204, tags=["album"])
def delete_all_albums():
    global albums_db
    albums_db.clear()
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Все альбомы удалены"}


@app.delete("/delete_all_tracks", status_code=204, tags=["track"])
def delete_all_tracks():
    global tracks_db
    tracks_db.clear()
    update_openapi_schema(app)  # Обновляем OpenAPI схему после изменений
    return {"detail": "Все треки удалены"}


# Запуск приложения
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
