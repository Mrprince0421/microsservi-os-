# product-service/app/models.py
from sqlalchemy.orm import Mapped, registry, mapped_column

table_registry = registry()


@table_registry.mapped_as_dataclass
class Product:
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int]  # Apenas o ID, sem ForeignKey
    name: Mapped[str]
    description: Mapped[str | None]
    price: Mapped[float]
    QT: Mapped[int] = mapped_column(name='qt')