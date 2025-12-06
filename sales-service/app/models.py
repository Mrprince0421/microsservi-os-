# sales-service/app/models.py
from datetime import datetime
from sqlalchemy.orm import Mapped, registry, mapped_column
from sqlalchemy import func

table_registry = registry()


@table_registry.mapped_as_dataclass
class Sale:
    __tablename__ = 'sales'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int]  # ID do usuário, sem chave estrangeira
    total_price: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )


@table_registry.mapped_as_dataclass
class SaleItem:
    __tablename__ = 'sale_items'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    sale_id: Mapped[int]  # Será preenchido após a venda ser criada
    product_id: Mapped[int] # ID do produto, sem chave estrangeira
    QT: Mapped[int] = mapped_column(name='qt')
    product_price: Mapped[float] # Preço no momento da venda