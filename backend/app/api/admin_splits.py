"""
api/admin_splits.py
===================
CRUD de splits/contrasplits por valor. Solo administradores.

GET    /admin/securities/{security_id}/splits  — lista los splits de un valor.
POST   /admin/securities/{security_id}/splits  — registra un nuevo split.
DELETE /admin/splits/{split_id}                — elimina un split.
GET    /admin/splits/detect                    — splits NO registrados, detectados
                                                 sobre las carteras de TODOS los
                                                 usuarios.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date as date_type, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import Position, PriceHistory, Security, SecuritySplit, TransactionRow, User
from app.schemas.market_admin import SplitIn, SplitOut
from app.services.calculations import Split, Transaction, normalize_splits

# Un precio pagado y el cierre de ESE dia no se separan mas de esto por
# variacion intradia. Por encima, la escala de la serie no es la de la
# operacion, y eso solo lo explica un evento corporativo sin registrar.
_UMBRAL_DESCUADRE = Decimal("2")

# Margen hacia atras al cargar cotizaciones: cubre el fin de semana o festivo
# anterior a una operacion hecha en un dia sin cierre propio.
_MARGEN_DIAS = 10

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/securities/{security_id}/splits", response_model=list[SplitOut])
def list_splits(
    security_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    rows = db.scalars(
        select(SecuritySplit)
        .where(SecuritySplit.security_id == security_id)
        .order_by(SecuritySplit.ex_date)
    ).all()
    return rows


@router.post(
    "/securities/{security_id}/splits",
    response_model=SplitOut,
    status_code=status.HTTP_201_CREATED,
)
def create_split(
    security_id: int,
    body: SplitIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    row = SecuritySplit(
        security_id=security_id,
        ex_date=body.ex_date.isoformat(),
        ratio_num=body.ratio_num,
        ratio_den=body.ratio_den,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/splits/detect")
def detect_unregistered_splits(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Splits/contrasplits NO registrados, buscados en las carteras de TODOS.

    Por que hace falta: las cotizaciones de Yahoo llegan SIEMPRE ajustadas por
    splits (auto_adjust solo gobierna los dividendos). Si el evento no esta en
    'security_splits', el numero de acciones se queda en unidades viejas contra
    precios ya reescalados y la valoracion se va por el factor del split. Un
    contrasplit 1:25 sin registrar convirtio una posicion de 1.500 EUR en 38.000
    y metio un pico de ~68.000 EUR en el grafico de un usuario.

    Y no lo detectaba nada: /history/coverage solo mira datos que FALTAN, y esto
    no es un dato ausente sino incoherente. La curva sale completa y creible, solo
    que falsa. Se encontro a mano.

    Criterio: para cada operacion se compara el precio pagado con el cierre de
    ese mismo dia. Deberian parecerse (variacion intradia). Si se separan por mas
    de x2 de forma consistente, la serie esta en otra escala que la operacion.

    Los precios se comparan YA NORMALIZADOS con normalize_splits, asi que un
    split correctamente dado de alta NO aparece aqui: solo sale lo que falta.
    """
    filas = db.execute(
        select(
            Security.id, Security.yahoo_ticker, Security.name, Security.market,
            User.username, Position.id,
            TransactionRow.date, TransactionRow.type,
            TransactionRow.shares, TransactionRow.price,
            TransactionRow.fee, TransactionRow.exchange_rate,
        )
        .join(Position, Position.security_id == Security.id)
        .join(User, User.id == Position.user_id)
        .join(TransactionRow, TransactionRow.position_id == Position.id)
        .where(TransactionRow.type.in_(("buy", "sell")))
        .order_by(Security.id, Position.id, TransactionRow.date)
    ).all()
    if not filas:
        return {"detected": []}

    # Splits ya registrados, para normalizar antes de comparar.
    splits_por_sec: dict[int, list[Split]] = defaultdict(list)
    for sp in db.scalars(select(SecuritySplit)).all():
        splits_por_sec[sp.security_id].append(
            Split(ex_date=date_type.fromisoformat(sp.ex_date),
                  ratio_num=sp.ratio_num, ratio_den=sp.ratio_den)
        )

    # Cotizaciones de los valores implicados, acotadas al periodo con
    # operaciones (una sola consulta, no una por transaccion).
    rango: dict[int, tuple[str, str]] = {}
    for sid, _tk, _nm, _mk, _u, _pid, d, *_ in filas:
        lo, hi = rango.get(sid, (d, d))
        rango[sid] = (min(lo, d), max(hi, d))
    precios: dict[int, tuple[list[str], list[Decimal]]] = {}
    if rango:
        acum: dict[int, list[tuple[str, Decimal]]] = defaultdict(list)
        for sid, d, c in db.execute(
            select(PriceHistory.security_id, PriceHistory.date, PriceHistory.close)
            .where(or_(*[
                and_(PriceHistory.security_id == sid,
                     PriceHistory.date >= (date_type.fromisoformat(lo)
                                           - timedelta(days=_MARGEN_DIAS)).isoformat(),
                     PriceHistory.date <= hi)
                for sid, (lo, hi) in rango.items()
            ]))
            .order_by(PriceHistory.security_id, PriceHistory.date)
        ).all():
            acum[sid].append((d, c))
        precios = {sid: ([x[0] for x in v], [x[1] for x in v]) for sid, v in acum.items()}

    # Normalizar por POSICION (normalize_splits opera sobre una lista de tx).
    por_posicion: dict[tuple[int, int, str], list] = defaultdict(list)
    meta: dict[int, tuple[str, str, str]] = {}
    for sid, tk, nm, mk, usuario, pid, d, tp, sh, pr, fee, er in filas:
        meta[sid] = (tk, nm, mk)
        por_posicion[(sid, pid, usuario)].append(
            Transaction(type=tp, date=date_type.fromisoformat(d), shares=sh,
                        price=pr, fee=fee, exchange_rate=er)
        )

    sospechas: dict[int, dict] = {}
    for (sid, _pid, usuario), txs in por_posicion.items():
        fechas, cierres = precios.get(sid, ([], []))
        if not fechas:
            continue
        for t in normalize_splits(txs, splits_por_sec.get(sid, [])):
            if t.price <= 0:
                continue
            iso = t.date.isoformat()
            i = bisect.bisect_right(fechas, iso) - 1
            if i < 0:
                continue
            ratio = cierres[i] / t.price
            if _UMBRAL_DESCUADRE > ratio > 1 / _UMBRAL_DESCUADRE:
                continue
            tk, nm, mk = meta[sid]
            ent = sospechas.setdefault(sid, {
                "security_id": sid, "ticker": tk, "name": nm, "market": mk,
                "registered_splits": len(splits_por_sec.get(sid, [])),
                "users": set(), "samples": [],
            })
            ent["users"].add(usuario)
            ent["samples"].append({
                "date": iso, "paid": str(t.price),
                "close": str(cierres[i]), "ratio": float(round(ratio, 3)),
            })

    detected = []
    for ent in sospechas.values():
        ratios = sorted(x["ratio"] for x in ent["samples"])
        mediana = ratios[len(ratios) // 2]
        # ratio = cierre/pagado = ratio_den/ratio_num.
        #   25   -> contrasplit 1:25   (acciones /25, precio x25)
        #   0,5  -> split       2:1    (acciones x2,  precio /2)
        if mediana >= 1:
            num, den = 1, max(2, round(mediana))
        else:
            num, den = max(2, round(1 / mediana)), 1
        ent["users"] = sorted(ent["users"])
        ent["samples"] = sorted(ent["samples"], key=lambda x: x["date"])[:6]
        ent["factor"] = float(round(Decimal(str(mediana)), 3))
        ent["suggested_ratio_num"] = num
        ent["suggested_ratio_den"] = den
        detected.append(ent)

    detected.sort(key=lambda e: -len(e["users"]))
    return {"detected": detected}


@router.delete("/splits/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(
    split_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(SecuritySplit, split_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split no encontrado")
    db.delete(row)
    db.commit()
