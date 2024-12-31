from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union
from pathlib import Path
import mimetypes


class ObjectType(Enum):
    POINT = 'point'
    LINEAR = 'linear'
    STATIONARY = 'stationary'


@dataclass
class Coordinate:
    id: Optional[int]
    object_id: int
    x: float
    y: float
    order_index: int


@dataclass
class Object:
    id: Optional[int]
    image_id: int
    name: str
    R1: float
    R2: float
    R3: float
    R4: float
    R5: float
    R6: float
    object_type: ObjectType
    coordinates: List[Coordinate]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def validate_coordinates(self) -> bool:
        """Проверяет корректность координат в зависимости от типа объекта"""
        if self.object_type == ObjectType.POINT:
            return len(self.coordinates) == 1

        elif self.object_type == ObjectType.LINEAR:
            return len(self.coordinates) >= 2

        elif self.object_type == ObjectType.STATIONARY:
            if len(self.coordinates) < 3:
                return False
            first = self.coordinates[0]
            last = self.coordinates[-1]
            return abs(first.x - last.x) < 1e-6 and abs(first.y - last.y) < 1e-6

        return False


@dataclass
class Image:
    id: Optional[int]
    file_name: str
    image_data: bytes
    scale: Optional[float]
    mime_type: Optional[str]
    file_size: Optional[int]
    objects: List[Object]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_file(cls, file_path: Union[str, Path], scale: float = 1.0) -> 'Image':
        """Создает объект Image из файла изображения"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_path} not found")

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith('image/'):
            raise ValueError(f"File {file_path} is not an image")

        with open(file_path, 'rb') as f:
            image_data = f.read()

        return cls(
            id=None,
            file_name=file_path.name,
            image_data=image_data,
            scale=scale,
            mime_type=mime_type,
            file_size=len(image_data),
            objects=[]
        )

    def save_to_file(self, output_path: Union[str, Path]):
        """Сохраняет изображение в файл"""
        output_path = Path(output_path)
        with open(output_path, 'wb') as f:
            f.write(self.image_data)