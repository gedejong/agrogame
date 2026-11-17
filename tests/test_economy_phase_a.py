"""Economy Phase A — seed charging, harvest quarter and nutrient pricing (#508).

Three bugs, three groups:

* seed was never charged in the catalog flow (games start pre-planted, and each
  new season replants automatically, so the manual ``plant`` action — the only
  thing that charged seed — never ran);
* ``settle_season`` was always called with the default ``quarter=3``, leaving
  the Q1/Q2/Q4 seasonal multipliers inert;
* fertilizer was priced per kg of *product* while the engine applies kg of
  *nutrient element*, and an unpriced type silently fell back to 1 cr/kg.

The seed group runs two full season cycles: a per-season charge that is applied
once at game creation and then never again is indistinguishable from a correct
one over a single season.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

# The API extra (fastapi, httpx) is absent from CI jobs that install only the
# base package, e.g. the benchmark job; skip the module there, as test_api does.
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.routes import (  # noqa: E402
    _FERTILIZER_NUTRIENT,
    _compute_action_cost,
    _harvest_product,
    _quarter_of,
    _seed_cost_per_ha,
    fertilizer_price_key,
)
from agrogame.api.state import games  # noqa: E402
from agrogame.game.economy import PriceTable  # noqa: E402

#: The default catalog scenario (three NL maize patches) — the flow that never
#: charged seed, because it arrives pre-planted.
NL_MAIZE_PATCHES = [
    {
        "soil_profile_key": "sandy_temperate",
        "crop_key": "maize",
        "climate_key": "netherlands_temperate",
        "area_fraction": 0.333,
    },
    {
        "soil_profile_key": "loam_temperate",
        "crop_key": "maize",
        "climate_key": "netherlands_temperate",
        "area_fraction": 0.334,
    },
    {
        "soil_profile_key": "clay_temperate",
        "crop_key": "maize",
        "climate_key": "netherlands_temperate",
        "area_fraction": 0.333,
    },
]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def prices() -> PriceTable:
    return PriceTable.load()


def _create_game(client: TestClient, patches: list[dict], credits: int = 50_000) -> str:
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": [{"field_id": "field_1", "patches": patches}],
            "starting_credits": credits,
        },
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["game_id"])


def _seed_costs(game_id: str) -> list[int]:
    return [
        c.amount_credits for c in games[game_id].ledger.costs if c.category == "seed"
    ]


# ---------------------------------------------------------------------------
# Seed is charged at season start, every season (AC3)
# ---------------------------------------------------------------------------
class TestSeedCharging:
    def test_catalog_game_charges_seed_at_creation(
        self, client: TestClient, prices: PriceTable
    ) -> None:
        """A pre-planted catalog game pays for its seed before day 1."""
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        charges = _seed_costs(game_id)
        assert len(charges) == 3, "one charge per planted patch"
        # Per-ha seed scaled by area_fraction; the three fractions sum to 1.0,
        # so the total is the per-ha price to within per-patch rounding.
        expected = prices.input_costs["seed_maize"]
        assert sum(charges) == pytest.approx(expected, abs=3)

    def test_bare_patch_is_not_charged(self, client: TestClient) -> None:
        """An unplanted patch buys no seed."""
        patches = [dict(NL_MAIZE_PATCHES[1], crop_key="", area_fraction=1.0)]
        game_id = _create_game(client, patches)
        assert _seed_costs(game_id) == []

    def test_seed_charged_in_season_1_and_season_2(
        self, client: TestClient, prices: PriceTable
    ) -> None:
        """Two full cycles: the automatic replant pays for seed again (#508 AC3).

        A charge applied only at game creation would leave season 2 free, and a
        charge applied before ``reset_season`` would be wiped by it. Both
        failure modes are invisible in a single-season test.
        """
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        ledger = games[game_id].ledger

        client.post(f"/api/v1/games/{game_id}/start-season?days=120&seed=42")
        season_1 = _seed_costs(game_id)
        assert sum(season_1) == pytest.approx(
            prices.input_costs["seed_maize"], abs=3
        ), "season 1 seed missing — the catalog pre-planting was free"

        client.post(f"/api/v1/games/{game_id}/start-season?days=120&seed=42")
        season_2 = _seed_costs(game_id)
        assert season_2 == season_1, "season 2 replant must cost the same as season 1"
        assert ledger.season_costs >= sum(
            season_2
        ), "the season-2 seed charge must survive EconomicLedger.reset_season"

    def test_unpriced_crop_raises(self, prices: PriceTable) -> None:
        """An unpriced crop is a configuration error, not a free input."""
        with pytest.raises(ValueError, match="seed_quinoa"):
            _seed_cost_per_ha("quinoa", prices)

    def test_both_wheat_presets_are_priced(self, prices: PriceTable) -> None:
        """`seed_wheat` was never a crop preset key, so wheat seed never priced."""
        assert _seed_cost_per_ha("winter_wheat", prices) > 0
        assert _seed_cost_per_ha("spring_wheat", prices) > 0


# ---------------------------------------------------------------------------
# Harvest quarter drives the seasonal multiplier (AC5)
# ---------------------------------------------------------------------------
class TestHarvestQuarter:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2024, 1, 1), 1),
            (date(2024, 3, 31), 1),
            (date(2024, 4, 1), 2),
            (date(2024, 6, 30), 2),
            (date(2024, 9, 30), 3),
            (date(2024, 12, 31), 4),
        ],
    )
    def test_quarter_of(self, day: date, expected: int) -> None:
        assert _quarter_of(day) == expected

    def test_q2_harvest_uses_the_q2_multiplier(
        self, client: TestClient, prices: PriceTable
    ) -> None:
        """A harvest in Q2 is paid at the Q2 price, not the hard-coded Q3 one.

        The session starts on 1 April (Q2), so a harvest a few days in settles
        in Q2. Maize's multipliers are [1.1, 0.9, 0.8, 1.2]: Q2 pays 0.9 and the
        old hard-coded Q3 paid 0.8, so the two are distinguishable.
        """
        patches = [dict(NL_MAIZE_PATCHES[1], area_fraction=1.0)]
        game_id = _create_game(client, patches)
        session = games[game_id]
        client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
        assert _quarter_of(session.current_date) == 2

        # Plant a known grain load so the settled revenue is exact.
        patch = next(iter(session.field_manager.fields.values())).patches[0]
        patch.orch.canopy.state.grain_biomass_g_m2 = 500.0

        resp = client.post(
            f"/api/v1/games/{game_id}/action",
            json={"field_id": "field_1", "action": "harvest", "params": {}},
        )
        assert resp.status_code == 200, resp.text
        q2_price = prices.get_crop_price("maize", quarter=2)
        q3_price = prices.get_crop_price("maize", quarter=3)
        assert resp.json()["revenue_credits"] == int(500.0 * 10.0 * q2_price)
        assert int(500.0 * 10.0 * q2_price) != int(500.0 * 10.0 * q3_price)

    @pytest.mark.parametrize(
        ("crop_key", "climate_key"),
        [("maize", "netherlands_temperate"), ("grape", "kenya_highlands")],
    )
    def test_report_settles_standing_crop_at_its_quarter(
        self, client: TestClient, prices: PriceTable, crop_key: str, climate_key: str
    ) -> None:
        """``GET /report`` settles still-standing patches at the current quarter.

        This is the client's own path: ``farm_view.gd`` calls ``/report`` after
        every harvest action, so harvesting one patch of a two-patch field
        settles the other through ``_settle_standing_grain``. The session starts
        on 1 April, so the report lands in Q2. Maize pays 0.9 in Q2 against the
        old hard-coded Q3's 0.8; grape, settled on sold fruit since #448, pays
        0.9 against 1.2, so the quarter and the dry-matter fraction are pinned
        together on the one path neither was tested on.
        """
        patch = {
            "soil_profile_key": "loam_temperate",
            "crop_key": crop_key,
            "climate_key": climate_key,
            "area_fraction": 0.5,
        }
        game_id = _create_game(client, [patch, dict(patch)])
        session = games[game_id]
        client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
        assert _quarter_of(session.current_date) == 2

        harvested, standing = next(iter(session.field_manager.fields.values())).patches
        harvested.orch.canopy.state.grain_biomass_g_m2 = 300.0
        standing.orch.canopy.state.grain_biomass_g_m2 = 400.0

        # Harvest patch 0 only; patch 1 stays standing for /report to settle.
        resp = client.post(
            f"/api/v1/games/{game_id}/action",
            json={
                "field_id": "field_1",
                "action": "harvest",
                "params": {"patch_idx": 0},
            },
        )
        assert resp.status_code == 200, resp.text
        assert standing.config.crop_key == crop_key
        revenue_before = session.ledger.season_revenue

        report = client.get(f"/api/v1/games/{game_id}/report")
        assert report.status_code == 200, report.text
        assert standing.orch.canopy.state.grain_biomass_g_m2 == 0.0

        dmf = _harvest_product(crop_key, climate_key).dry_matter_fraction
        sold_kg = 400.0 * 10.0 / dmf * 0.5
        q2_revenue = int(sold_kg * prices.get_crop_price(crop_key, quarter=2))
        q3_revenue = int(sold_kg * prices.get_crop_price(crop_key, quarter=3))
        assert report.json()["revenue_credits"] - revenue_before == q2_revenue
        assert q2_revenue != q3_revenue


# ---------------------------------------------------------------------------
# Fertilizer is priced per kg of nutrient element (AC1)
# ---------------------------------------------------------------------------
class TestFertilizerPricing:
    @pytest.mark.parametrize(
        ("fert_type", "expected"),
        [
            ("urea", "fertilizer_urea_per_kg_N"),
            ("ammonium_nitrate", "fertilizer_ammonium_nitrate_per_kg_N"),
            ("tsp", "fertilizer_tsp_per_kg_P"),
            ("gypsum", "fertilizer_gypsum_per_kg_S"),
            ("elemental_s", "fertilizer_elemental_s_per_kg_S"),
        ],
    )
    def test_price_key_names_the_nutrient_element(
        self, fert_type: str, expected: str
    ) -> None:
        """Every engine-supported type maps to a per-kg-of-element key.

        The engine applies the rate as kg N, kg P or kg S, so the key must say
        so; `fertilizer_<type>` priced per kg of *product* was the bug.
        """
        assert fertilizer_price_key(fert_type) == expected

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown fertilizer type"):
            fertilizer_price_key("guano")

    def test_unpriced_fertilizer_raises_rather_than_costing_one(
        self, prices: PriceTable
    ) -> None:
        """No fallback: an unpriced type used to cost 1 cr/kg, making S free."""
        missing = PriceTable(
            input_costs={"labor_per_action": 50.0}, crop_prices=prices.crop_prices
        )
        with pytest.raises(ValueError, match="fertilizer_urea_per_kg_N"):
            _compute_action_cost(
                "fertilize", {"type": "urea", "amount_kg_ha": 50.0}, missing
            )

    def test_fertilize_cost_is_labor_plus_price_times_kg_nutrient(
        self, prices: PriceTable
    ) -> None:
        """Cost = labor + price_per_kg_nutrient × kg of nutrient applied."""
        table = PriceTable(
            input_costs={
                "labor_per_action": 50.0,
                "fertilizer_urea_per_kg_N": 2.17,
            },
            crop_prices=prices.crop_prices,
        )
        cost = _compute_action_cost(
            "fertilize", {"type": "urea", "amount_kg_ha": 50.0}, table
        )
        # 50 + 2.17 × 50 = 158.5, truncated to 158 — a deliberately
        # non-integral unit price, since /action/preview must agree exactly
        # with the ledger deduction at non-integral costs (#465).
        assert cost == 158

    def test_unpriced_fertilizer_is_a_400_not_a_500(self, client: TestClient) -> None:
        """The API surfaces a missing price as a client error, not a crash."""
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        resp = client.post(
            f"/api/v1/games/{game_id}/action/preview",
            json={
                "field_id": "field_1",
                "action": "fertilize",
                "params": {"type": "guano", "amount_kg_ha": 50.0},
            },
        )
        assert resp.status_code == 400
        assert "guano" in resp.text


# ---------------------------------------------------------------------------
# The Godot picker's prices cannot drift from prices.yaml (AC2)
# ---------------------------------------------------------------------------
_PICKER_GD = (
    Path(__file__).resolve().parents[1] / "game" / "scripts" / "fertilizer_picker.gd"
)


def _gd_dict_const(source: str, name: str) -> dict[str, str]:
    """Entries of a ``const NAME := {"key": value, ...}`` block in GDScript."""
    match = re.search(rf"^const {name} := \{{(.*?)^\}}", source, re.S | re.M)
    if match is None:
        raise ValueError(f"const {name} not found in {_PICKER_GD}")
    return dict(re.findall(r'"(\w+)":\s*"?([\w.]+)"?', match.group(1)))


def _gd_int_const(source: str, name: str) -> int:
    """Value of a ``const NAME := <int>`` line in GDScript."""
    match = re.search(rf"^const {name}(?::\s*int)? := (\d+)$", source, re.M)
    if match is None:
        raise ValueError(f"const {name} not found in {_PICKER_GD}")
    return int(match.group(1))


class TestPickerParity:
    """``FertilizerPicker`` hand-copies the price table; these keep it honest.

    The client computes its cost labels locally, so its constants duplicate
    ``data/economy/prices.yaml``. GUT pins the picker's costs to literals but
    never reads the YAML, and the rest of the Python suite never reads the
    GDScript, so editing one side alone used to leave every test green while
    the picker showed one price and ``/action`` charged another. Phase B (#438)
    edits exactly these numbers.
    """

    @pytest.mark.parametrize(
        ("fert_type", "amount_kg_ha", "expected"),
        [
            ("urea", 50.0, 123),
            ("ammonium_nitrate", 50.0, 231),
            ("tsp", 50.0, 286),
            ("tsp", 100.0, 523),
            ("tsp", 25.0, 168),
        ],
    )
    def test_preview_and_action_charge_the_picker_pinned_cost(
        self,
        client: TestClient,
        fert_type: str,
        amount_kg_ha: float,
        expected: int,
    ) -> None:
        """The shipped table charges what the picker shows.

        The same literals are pinned on the client side in
        ``game/tests/unit/test_fertilizer_picker.gd``
        (``test_cost_matches_backend_formula`` and
        ``test_cost_truncates_like_the_backend_at_a_non_integral_cost``).
        Urea 50 kg N is 50 + 1.47 × 50 = 123.5 and TSP 25 kg P is 168.25, so
        those two also pin truncation rather than rounding.
        """
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        body = {
            "field_id": "field_1",
            "action": "fertilize",
            "params": {"type": fert_type, "amount_kg_ha": amount_kg_ha},
        }
        preview = client.post(f"/api/v1/games/{game_id}/action/preview", json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json()["cost_credits"] == expected

        before = games[game_id].ledger.balance_credits
        resp = client.post(f"/api/v1/games/{game_id}/action", json=body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["cost_credits"] == expected
        assert resp.json()["balance_credits"] == before - expected

    def test_picker_constants_match_the_price_table(self, prices: PriceTable) -> None:
        """Every picker constant equals its ``prices.yaml`` / routes counterpart."""
        source = _PICKER_GD.read_text(encoding="utf-8")
        offered = re.search(r"^const TYPES: Array\[String\] = \[(.*)\]$", source, re.M)
        assert offered is not None, "const TYPES not found"
        types = re.findall(r'"(\w+)"', offered.group(1))
        gd_prices = _gd_dict_const(source, "PRICE_PER_KG_NUTRIENT")
        gd_nutrients = _gd_dict_const(source, "NUTRIENTS")

        assert types, "picker offers no fertiliser types"
        assert set(gd_prices) == set(types)
        for fert_type in types:
            assert gd_nutrients[fert_type] == _FERTILIZER_NUTRIENT[fert_type]
            key = fertilizer_price_key(fert_type)
            assert float(gd_prices[fert_type]) == prices.input_costs[key], key
        assert (
            _gd_int_const(source, "LABOR_PER_ACTION")
            == prices.input_costs["labor_per_action"]
        )
