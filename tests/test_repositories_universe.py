from app.repositories.universe import UniverseRepository
from tests.utils import build_session


def test_universe_repository_runtime_tickers_filter():
    repo = UniverseRepository()
    with build_session() as db:
        repo.upsert_symbol(
            db,
            ticker="005930",
            name="Samsung",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="000660",
            name="SK",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=True,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="035420",
            name="Naver",
            market="KOSPI200",
            in_universe=False,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="068270",
            name="Celltrion",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="halted",
        )

        tickers = repo.list_runtime_tickers(db)
        assert tickers == ["005930"]


def test_universe_repository_tracking_tickers_include_blocked_active():
    repo = UniverseRepository()
    with build_session() as db:
        repo.upsert_symbol(
            db,
            ticker="005930",
            name="Samsung",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="000660",
            name="SK",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=True,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="068270",
            name="Celltrion",
            market="KOSPI200",
            in_universe=True,
            is_active=False,
            is_blocked=False,
            status="normal",
        )

        tracking = repo.list_tracking_tickers(db)
        trading = repo.list_trading_tickers(db)
        whole = repo.list_universe_tickers(db)

        assert tracking == ["000660", "005930"]
        assert trading == ["005930"]
        assert whole == ["000660", "005930", "068270"]


def test_universe_repository_list_and_block_update():
    repo = UniverseRepository()
    with build_session() as db:
        repo.upsert_symbol(
            db,
            ticker="005930",
            name="Samsung",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        repo.upsert_symbol(
            db,
            ticker="000660",
            name="SK",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        all_rows = repo.list_symbols(db)
        assert [x.ticker for x in all_rows] == ["000660", "005930"]

        runtime_rows = repo.list_symbols(db, runtime_only=True)
        assert [x.ticker for x in runtime_rows] == ["000660", "005930"]

        repo.set_blocked(db, ticker="000660", blocked=True)
        runtime_rows_after = repo.list_symbols(db, runtime_only=True)
        assert [x.ticker for x in runtime_rows_after] == ["005930"]

        filtered = repo.list_symbols(db, market="KOSPI200", is_blocked=False, ticker_query="sams", limit=10, offset=0)
        assert [x.ticker for x in filtered] == ["005930"]
