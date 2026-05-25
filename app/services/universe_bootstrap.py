from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from http.cookiejar import CookieJar
from logging import Logger
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request as UrlRequest, build_opener

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models.candle import Candle as CandleRow
from app.db.models.universe import Symbol
from app.domain.universe_status import UniverseStatus


_KRX_BASE_URL = "https://index.krx.co.kr"
_KRX_OTP_URL = f"{_KRX_BASE_URL}/contents/COM/GenerateOTP.jspx"
_KRX_DATA_URL = f"{_KRX_BASE_URL}/contents/IDX/99/IDX99000001.jspx"
_KRX_INDEX_PAGE_BASE_URL = f"{_KRX_BASE_URL}/contents/MKD/03/0304/03040101/MKD03040101.jsp"
_KRX_INDEX_DEFAULT_REFERER = f"{_KRX_INDEX_PAGE_BASE_URL}?upmidCd=0102&idxCd=1028&idxId=K2G01P"
_KRX_INDEX_PAGE_PATH = "/contents/MKD/03/0304/03040101/MKD03040101T3.jsp"
_KRX_INDEX_BLD = "/IDX/03/0304/03040101/mkd03040101T3_01"
_VALID_UNIVERSE_SOURCES = {"KOSPI200", "KOSDAQ150", "USER"}


def normalize_universe_source(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    legacy_map = {
        "KOSPI": "KOSPI200",
        "KOSDAQ": "KOSDAQ150",
        "UNKNOWN": "USER",
        "": "USER",
    }
    normalized = legacy_map.get(normalized, normalized)
    if normalized in _VALID_UNIVERSE_SOURCES:
        return normalized
    return None


def _krx_headers(*, referer: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": _KRX_BASE_URL,
        "Referer": referer,
    }


def _decode_krx_body(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _krx_get(opener: OpenerDirector, *, url: str) -> None:
    req = UrlRequest(url, headers=_krx_headers(referer=url), method="GET")
    with opener.open(req, timeout=15):
        return


def _krx_post_form(
    opener: OpenerDirector,
    *,
    url: str,
    data: dict[str, str],
    referer: str,
) -> str:
    payload = urlencode(data).encode("utf-8")
    req = UrlRequest(url, data=payload, headers=_krx_headers(referer=referer), method="POST")
    with opener.open(req, timeout=15) as resp:
        return _decode_krx_body(resp.read())


def _krx_generate_otp(opener: OpenerDirector, *, bld: str, referer: str) -> str:
    otp = _krx_post_form(
        opener,
        url=_KRX_OTP_URL,
        data={
            "name": "form",
            "bld": bld,
        },
        referer=referer,
    ).strip()
    if not otp:
        raise ValueError(f"krx_otp_empty:{bld}")
    return otp


def _krx_post_json_with_otp(
    opener: OpenerDirector,
    *,
    otp: str,
    data: dict[str, str],
    referer: str,
) -> dict[str, object]:
    raw = _krx_post_form(
        opener,
        url=_KRX_DATA_URL,
        data={"code": otp, **data},
        referer=referer,
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"krx_json_decode_error:{exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("krx_json_not_object")
    return parsed


def _krx_json_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    for key in ("block1", "output", "DS1", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _krx_latest_trading_date(opener: OpenerDirector) -> str:
    referer = _KRX_INDEX_DEFAULT_REFERER
    otp = _krx_generate_otp(opener, bld="/COM/market_date_t", referer=referer)
    payload = _krx_post_json_with_otp(
        opener,
        otp=otp,
        data={"pagePath": _KRX_INDEX_PAGE_PATH},
        referer=referer,
    )
    rows = _krx_json_rows(payload)
    for row in rows:
        raw_date = str(row.get("max_work_dt", "")).strip()
        if len(raw_date) == 8 and raw_date.isdigit():
            return raw_date
    raise ValueError("krx_market_date_missing")


def _krx_fetch_index_constituents(
    opener: OpenerDirector,
    *,
    market: str,
    idx_id: str,
    idx_cd: str,
    upmid_cd: str,
    ind_tp_cd: str,
    idx_ind_cd: str,
    trade_date: str,
) -> list[dict[str, str]]:
    referer = f"{_KRX_INDEX_PAGE_BASE_URL}?upmidCd={upmid_cd}&idxCd={idx_cd}&idxId={idx_id}"
    _krx_get(opener, url=referer)
    otp = _krx_generate_otp(opener, bld=_KRX_INDEX_BLD, referer=referer)
    payload = _krx_post_json_with_otp(
        opener,
        otp=otp,
        data={
            "ind_tp_cd": ind_tp_cd,
            "idx_ind_cd": idx_ind_cd,
            "idx_id": idx_id,
            "idxCd": idx_cd,
            "upmidCd": upmid_cd,
            "lang": "ko",
            "compst_isu_tp": "1",
            "schdate": trade_date,
            "fromdate": trade_date,
            "todate": trade_date,
            "pagePath": _KRX_INDEX_PAGE_PATH,
        },
        referer=referer,
    )
    rows = _krx_json_rows(payload)
    by_ticker: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = str(row.get("isu_cd") or row.get("ISU_CD") or "").strip().upper()
        if not ticker:
            continue
        name = str(
            row.get("isu_nm")
            or row.get("ISU_NM")
            or row.get("isu_abbrv")
            or row.get("ISU_ABBRV")
            or ticker
        ).strip() or ticker
        by_ticker[ticker] = {"ticker": ticker, "name": name, "market": market}
    return [by_ticker[t] for t in sorted(by_ticker.keys())]


def fetch_prd_initial_universe_seed() -> dict[str, object]:
    """
    PRD 2.2 기준: 최초 전체 유니버스는 코스피200 + 코스닥150.
    """
    try:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        _krx_get(opener, url=_KRX_INDEX_DEFAULT_REFERER)
        trade_date = _krx_latest_trading_date(opener)

        kospi200_items = _krx_fetch_index_constituents(
            opener,
            market="KOSPI200",
            idx_id="K2G01P",
            idx_cd="1028",
            upmid_cd="0102",
            ind_tp_cd="1",
            idx_ind_cd="028",
            trade_date=trade_date,
        )
        kosdaq150_items = _krx_fetch_index_constituents(
            opener,
            market="KOSDAQ150",
            idx_id="Q5G01P",
            idx_cd="2203",
            upmid_cd="0103",
            ind_tp_cd="2",
            idx_ind_cd="203",
            trade_date=trade_date,
        )

        if len(kospi200_items) != 200:
            return {"ok": False, "error": f"constituent_count_mismatch:kospi200={len(kospi200_items)}"}
        if len(kosdaq150_items) != 150:
            return {"ok": False, "error": f"constituent_count_mismatch:kosdaq150={len(kosdaq150_items)}"}

        by_ticker: dict[str, dict[str, str]] = {}
        for item in kospi200_items + kosdaq150_items:
            ticker = str(item.get("ticker", "")).strip()
            if not ticker:
                continue
            by_ticker[ticker] = item
        items = [by_ticker[ticker] for ticker in sorted(by_ticker.keys())]
        if len(items) != 350:
            return {"ok": False, "error": f"constituent_union_count_mismatch:{len(items)}"}
        return {
            "ok": True,
            "items": items,
            "meta": {
                "source": "krx_index_t3",
                "trade_date": trade_date,
                "kospi200_count": len(kospi200_items),
                "kosdaq150_count": len(kosdaq150_items),
                "union_count": len(items),
            },
        }
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"seed_fetch_network_or_parse_error:{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"seed_fetch_exception:{exc}"}


def migrate_universe_source_labels(
    *,
    session_factory,
    universe_repo,
    normalize_source: Callable[[str | None], str | None],
    logger: Logger | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {"attempted": True, "updated_count": 0}
    try:
        with session_factory() as db:
            rows = universe_repo.list_symbols(db, limit=20_000)
            updated = 0
            for row in rows:
                normalized = normalize_source(row.market)
                if normalized is None:
                    normalized = "USER"
                if row.market != normalized:
                    row.market = normalized
                    updated += 1
            if updated > 0:
                db.commit()
            result["updated_count"] = updated
            result["ok"] = True
            result["message"] = f"normalized:{updated}"
            if updated > 0 and logger is not None:
                logger.info("universe_source_labels_normalized updated=%s", updated)
            return result
    except SQLAlchemyError as exc:
        return {"attempted": True, "ok": False, "message": f"db_error:{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"attempted": True, "ok": False, "message": f"error:{exc}"}


def candle_bootstrap_coverage(
    db,
    *,
    universe_repo,
    timeframes: tuple[str, ...],
) -> dict[str, object]:
    in_universe_count = universe_repo.count_symbols(db, in_universe=True)
    per_timeframe: dict[str, int] = {}
    for timeframe in timeframes:
        ticker_count = db.scalar(
            select(func.count(func.distinct(CandleRow.ticker)))
            .select_from(CandleRow)
            .join(Symbol, Symbol.ticker == CandleRow.ticker)
            .where(Symbol.in_universe.is_(True), CandleRow.timeframe == timeframe)
        )
        per_timeframe[timeframe] = int(ticker_count or 0)
    needs_bootstrap = in_universe_count > 0 and any(
        count < in_universe_count for count in per_timeframe.values()
    )
    return {
        "in_universe_count": in_universe_count,
        "per_timeframe_ticker_count": per_timeframe,
        "needs_bootstrap": needs_bootstrap,
    }


def recompute_active_universe_from_daily_liquidity(
    db,
    *,
    config_manager,
    universe_repo,
    candle_repo,
) -> dict[str, object]:
    threshold_eok = float(config_manager.get("liquidity_threshold"))
    threshold_won = threshold_eok * 100_000_000.0

    rows = universe_repo.list_symbols(db, in_universe=True, limit=20_000)
    active_count = 0
    updated_count = 0
    insufficient_daily_count = 0
    for row in rows:
        should_activate = False
        if row.status not in {
            UniverseStatus.HALTED.value,
            UniverseStatus.REMOVED.value,
            UniverseStatus.EXIT_PENDING.value,
        }:
            daily = candle_repo.list_recent(db, ticker=row.ticker, timeframe="1d", limit=20)
            if len(daily) >= 20:
                avg_value = sum(max(float(x.close), 0.0) * max(float(x.volume), 0.0) for x in daily) / len(daily)
                should_activate = avg_value >= threshold_won
            else:
                insufficient_daily_count += 1

        if row.is_active != should_activate:
            row.is_active = should_activate
            updated_count += 1
        if should_activate:
            active_count += 1
    return {
        "threshold_eok": threshold_eok,
        "threshold_won": threshold_won,
        "in_universe_count": len(rows),
        "active_count": active_count,
        "updated_count": updated_count,
        "insufficient_daily_count": insufficient_daily_count,
    }


async def bootstrap_candles_on_first_run(
    *,
    tickers: list[str],
    timeframes: tuple[str, ...],
    session_factory,
    candle_repo,
    kiwoom_app_key: str,
    kiwoom_app_secret: str,
    rate_limited_client_factory,
    kiwoom_api_client_factory,
    kiwoom_market_data_gateway_factory,
) -> dict[str, object]:
    status: dict[str, object] = {
        "attempted": True,
        "ok": False,
        "message": "not_started",
        "ticker_count": len(tickers),
        "timeframes": list(timeframes),
        "candles_inserted": 0,
        "candles_updated": 0,
        "tickers_with_candles": 0,
        "errors": [],
        "timeframe_stats": {tf: {"inserted": 0, "updated": 0, "tickers_with_data": 0} for tf in timeframes},
    }
    if not tickers:
        status["message"] = "skipped_no_tickers"
        status["ok"] = True
        return status
    if not kiwoom_app_key or not kiwoom_app_secret:
        status["message"] = "kiwoom_credentials_missing"
        return status

    client = kiwoom_api_client_factory(rate_limited_client_factory())
    try:
        await client.ensure_token()
    except Exception as exc:  # noqa: BLE001
        status["message"] = f"kiwoom_auth_failed:{exc}"
        return status
    market_data = kiwoom_market_data_gateway_factory(client)
    errors: list[str] = []
    for ticker in tickers:
        has_any = False
        for timeframe in timeframes:
            try:
                with session_factory() as db:
                    since = candle_repo.get_last_candle_time(db, ticker=ticker, timeframe=timeframe)
                candles = await market_data.fetch_candles_incremental(ticker=ticker, timeframe=timeframe, since=since)
                if not candles:
                    continue
                payload = [
                    {
                        "candle_time": x.ts,
                        "open": x.open,
                        "high": x.high,
                        "low": x.low,
                        "close": x.close,
                        "volume": x.volume,
                    }
                    for x in candles
                ]
                with session_factory() as db:
                    inserted, updated = candle_repo.upsert_batch(
                        db,
                        ticker=ticker,
                        timeframe=timeframe,
                        candles=payload,
                    )
                status["candles_inserted"] = int(status["candles_inserted"]) + inserted
                status["candles_updated"] = int(status["candles_updated"]) + updated
                tf_stats = status["timeframe_stats"].get(timeframe, {})
                tf_stats["inserted"] = int(tf_stats.get("inserted", 0)) + inserted
                tf_stats["updated"] = int(tf_stats.get("updated", 0)) + updated
                if (inserted + updated) > 0:
                    has_any = True
                    tf_stats["tickers_with_data"] = int(tf_stats.get("tickers_with_data", 0)) + 1
                status["timeframe_stats"][timeframe] = tf_stats
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{ticker}:{timeframe}:{exc}")
        if has_any:
            status["tickers_with_candles"] = int(status["tickers_with_candles"]) + 1

    status["errors"] = errors[:20]
    if int(status["tickers_with_candles"]) == 0:
        status["message"] = "no_candles_collected"
        return status
    if errors:
        status["message"] = f"partial_success:{len(errors)}"
    else:
        status["message"] = "completed"
    status["ok"] = True
    return status


def bootstrap_universe_on_first_run(
    *,
    session_factory,
    universe_repo,
    seed_fetcher: Callable[[], dict[str, object]],
    normalize_source: Callable[[str | None], str | None],
) -> dict[str, object]:
    status: dict[str, object] = {
        "attempted": True,
        "bootstrapped": False,
        "source": None,
        "message": "skipped",
    }
    try:
        with session_factory() as db:
            current_count = universe_repo.count_symbols(db)
            if current_count > 0:
                status["message"] = f"already_initialized:{current_count}"
                return status
        seeds = seed_fetcher()
        if not seeds.get("ok"):
            status["message"] = f"seed_fetch_failed:{seeds.get('error', 'unknown')}"
            return status
        items = seeds.get("items", [])
        if not isinstance(items, list) or not items:
            status["message"] = "seed_fetch_empty"
            return status

        seeded_count = 0
        with session_factory() as db:
            for item in items:
                ticker = str(item.get("ticker", "")).strip()
                if not ticker:
                    continue
                market = normalize_source(str(item.get("market", "")))
                if market is None:
                    status["message"] = f"bootstrap_error:invalid_market:{item.get('market')}"
                    return status
                name = str(item.get("name", ticker)).strip() or ticker
                db.add(
                    Symbol(
                        ticker=ticker,
                        name=name,
                        market=market,
                        in_universe=True,
                        is_active=False,
                        is_blocked=False,
                        status=UniverseStatus.NORMAL.value,
                    )
                )
                seeded_count += 1
            db.commit()

        status["bootstrapped"] = True
        status["source"] = "prd_index_constituents"
        status["message"] = f"bootstrapped:{seeded_count}"
        status["seeded_count"] = seeded_count
        return status
    except SQLAlchemyError as exc:
        status["message"] = f"bootstrap_db_error:{exc}"
        return status
    except Exception as exc:  # noqa: BLE001
        status["message"] = f"bootstrap_error:{exc}"
        return status
