"""
api/favorites.py
================
Valores marcados como favoritos por el usuario.

GET    /favorites             — lista de favoritos con snapshot.
POST   /favorites/{sec_id}    — marca un valor como favorito.
DELETE /favorites/{sec_id}    — quita de favoritos.
PATCH  /favorites/{sec_id}    — actualiza precio objetivo de compra.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Favorite, PriceSnapshot, Security, User

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteOut(BaseModel):
    security_id: int
    yahoo_ticker: str
    name: str
    currency: str
    target_buy_price: Decimal | None
    last_price: Decimal | None = None
    daily_change_pct: Decimal | None = None

    model_config = {"from_attributes": False}


class TargetPriceUpdate(BaseModel):
    target_buy_price: Decimal | None


@router.get("", response_model=list[FavoriteOut])
def list_favorites(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(Favorite)
        .where(Favorite.user_id == user.id)
        .join(Favorite.security)
        .order_by(Security.name)
    ).all()
    sec_ids = [f.security_id for f in rows]
    snaps: dict = {}
    if sec_ids:
        for snap in db.scalars(
            select(PriceSnapshot).where(PriceSnapshot.security_id.in_(sec_ids))
        ).all():
            snaps[snap.security_id] = snap
    return [
        FavoriteOut(
            security_id=f.security_id,
            yahoo_ticker=f.security.yahoo_ticker,
            name=f.security.name,
            currency=f.security.currency,
            target_buy_price=f.target_buy_price,
            last_price=snaps[f.security_id].last_price if f.security_id in snaps else None,
            daily_change_pct=snaps[f.security_id].daily_change_pct if f.security_id in snaps else None,
        )
        for f in rows
    ]


@router.post("/{security_id}", status_code=status.HTTP_201_CREATED)
def add_favorite(
    security_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    fav = Favorite(user_id=user.id, security_id=security_id)
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya es favorito")
    return {"detail": "Marcado como favorito"}


@router.delete("/{security_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    security_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fav = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.security_id == security_id,
        )
    )
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No es favorito")
    db.delete(fav)
    db.commit()


@router.patch("/{security_id}", response_model=FavoriteOut)
def update_target_price(
    security_id: int,
    body: TargetPriceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fav = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.security_id == security_id,
        )
    )
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No es favorito")
    fav.target_buy_price = body.target_buy_price
    db.commit()
    db.refresh(fav)
    snap = db.get(PriceSnapshot, fav.security_id)
    return FavoriteOut(
        security_id=fav.security_id,
        yahoo_ticker=fav.security.yahoo_ticker,
        name=fav.security.name,
        currency=fav.security.currency,
        target_buy_price=fav.target_buy_price,
        last_price=snap.last_price if snap else None,
        daily_change_pct=snap.daily_change_pct if snap else None,
    )
