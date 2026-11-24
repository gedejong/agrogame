"""Economy Phase A — seed charging, harvest quarter and nutrient pricing (#508).

Three bugs, three groups:

* seed was never charged in the catalog flow (games start pre-planted, and each
  new season replants automatically, so the manual ``plant`` action — the only
  thing that charged seed — never ran);
* ``settle_season`` was always called with the default ``quarter=3``, leaving
  the Q1/Q2/Q4 seasonal multipliers inert;
* fertilizer was priced per kg of *product* while the engine applies kg of
  *nutrient element*, and an unpriced type silently fell back to 1 cr/kg.

``TestPlantSeedByArea`` (#525) prices the ``plant`` action by the patches it sows.

The seed group runs two full season cycles: a per-season charge that is applied
once at game creation and then never again is indistinguishable from a correct
one over a single season.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

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
        """Every Run Season replant pays for seed again (#508 AC3).

        Drives the client's Run Season flow as it stands after #487
        (``api_client.run_season``): ``/start-season`` only sets a season up,
        ``/step`` drives it to ``season_complete``, and only then does the next
        ``/start-season`` reset and replant. Two back-to-back ``/start-season``
        calls never reach that reset, so they cannot test it.

        A charge applied only at game creation would leave later seasons free,
        and a charge applied before ``reset_season`` would be wiped by it. The
        balance is asserted as well as the cost entries, so the test stays
        honest if the lifecycle moves again. Three seasons, so two rollovers.
        """
        days = 120
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        ledger = games[game_id].ledger
        per_patch = [
            int(round(prices.input_costs["seed_maize"] * p["area_fraction"]))
            for p in NL_MAIZE_PATCHES
        ]

        # Season 1's seed is charged when the pre-planted game is created.
        assert _seed_costs(game_id) == per_patch, "season 1 seed missing"

        for season in (1, 2, 3):
            balance_before = ledger.balance_credits
            started = client.post(
                f"/api/v1/games/{game_id}/start-season?days={days}&seed=42"
            )
            assert started.status_code == 200, started.text
            if season == 1:
                # Already paid at creation; starting season 1 must not repeat it.
                assert ledger.balance_credits == balance_before
            else:
                charged = _seed_costs(game_id)
                assert charged == per_patch, f"season {season} replant was free"
                assert ledger.balance_credits == balance_before - sum(charged)
                assert ledger.season_costs >= sum(
                    charged
                ), "the seed charge must survive EconomicLedger.reset_season"

            stepped = client.post(f"/api/v1/games/{game_id}/step?days={days}")
            assert stepped.status_code == 200, stepped.text
            assert stepped.json()["season_complete"], f"season {season} unfinished"

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
    match = re.search(rf"^const {name}(?::\s*int)?\s*:?=\s*(\d+)$", source, re.M)
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


# ---------------------------------------------------------------------------
# Plant charges seed for the area it sows (#525)
# ---------------------------------------------------------------------------
#: Per-patch ``plant`` charge on the default field for each client crop
#: (``AVAILABLE_CROPS`` in farm_view.gd): seed per ha × ``area_fraction``,
#: rounded per patch. Grape's 166.5 on 0.333 rounds half-even to 166.
PLANT_CHARGES = {
    "maize": [67, 67, 67],
    "spring_wheat": [50, 50, 50],
    "sorghum": [40, 40, 40],
    "rice": [60, 60, 60],
    "grape": [166, 167, 166],
}


def _act(
    client: TestClient, game_id: str, action: str, params: dict, preview: bool = False
) -> Any:  # an httpx.Response
    path = "action/preview" if preview else "action"
    body = {"field_id": "field_1", "action": action, "params": params}
    return client.post(f"/api/v1/games/{game_id}/{path}", json=body)


_LIME_GD = Path(__file__).resolve().parents[1] / "game" / "scripts" / "lime_picker.gd"


def _step(client: TestClient, game_id: str, days: int) -> None:
    resp = client.post(f"/api/v1/games/{game_id}/step?days={days}&seed=42")
    assert resp.status_code == 200, resp.text


def _harvest(client: TestClient, game_id: str, params: dict) -> dict:
    resp = _act(client, game_id, "harvest", params)
    assert resp.status_code == 200, resp.text
    body: dict = resp.json()
    return body


def _harvest_all(client: TestClient, game_id: str) -> None:
    resp = _act(client, game_id, "harvest", {})
    assert resp.json()["status"] == "executed", resp.text


def _bare_default_field(client: TestClient, crop: str) -> tuple[str, list[int]]:
    """The default field sown with ``crop``, harvested bare.

    Returns the game id and the creation-time seed charge per patch.
    """
    game_id = _create_game(client, [dict(p, crop_key=crop) for p in NL_MAIZE_PATCHES])
    creation = _seed_costs(game_id)
    _harvest_all(client, game_id)
    return game_id, creation


class TestPlantSeedByArea:
    """``plant`` is priced by the patches it sows, like the creation charge.

    Only the creation-time charge and Plant on bare patches: no
    ``/start-season`` and no rollover, so #531's C6 (no season boundary) and C12
    (Plant needs a bare patch) leave these valid.
    """

    @pytest.mark.parametrize("crop", list(PLANT_CHARGES))
    def test_plant_on_a_patch_charges_its_creation_time_seed(
        self, client: TestClient, crop: str
    ) -> None:
        """AC1, over two plant → grow → harvest cycles."""
        game_id, creation = _bare_default_field(client, crop)
        assert creation == PLANT_CHARGES[crop]
        for cycle in (1, 2):
            for i, expected in enumerate(creation):
                before = games[game_id].ledger.balance_credits
                resp = _act(
                    client, game_id, "plant", {"crop_key": crop, "patch_idx": i}
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["cost_credits"] == expected, (cycle, i)
                assert before - resp.json()["balance_credits"] == expected, (cycle, i)
            assert client.post(f"/api/v1/games/{game_id}/step?days=10").is_success
            _harvest_all(client, game_id)

    def test_patch_by_patch_and_whole_field_cost_the_creation_charge(
        self, client: TestClient
    ) -> None:
        """AC2: 67 + 67 + 67 = 201, as is a whole-field plant (no or -1 index)."""
        game_id, creation = _bare_default_field(client, "maize")
        ledger = games[game_id].ledger
        before = ledger.balance_credits
        for i in range(3):
            _act(client, game_id, "plant", {"crop_key": "maize", "patch_idx": i})
        assert before - ledger.balance_credits == sum(creation) == 201
        for params in ({"crop_key": "maize"}, {"crop_key": "maize", "patch_idx": -1}):
            _harvest_all(client, game_id)
            resp = _act(client, game_id, "plant", params)
            assert resp.json()["cost_credits"] == 201, params

    def test_one_patch_field_pays_the_full_per_ha_price(
        self, client: TestClient, prices: PriceTable
    ) -> None:
        """AC2 and AC4: area 1.0 is the per-ha price, and the 3-argument call."""
        game_id = _create_game(client, [dict(NL_MAIZE_PATCHES[1], area_fraction=1.0)])
        _harvest_all(client, game_id)
        resp = _act(client, game_id, "plant", {"crop_key": "maize", "patch_idx": 0})
        assert resp.json()["cost_credits"] == _seed_costs(game_id)[0] == 200
        assert _compute_action_cost("plant", {"crop_key": "maize"}, prices) == 200
        areas = [p["area_fraction"] for p in NL_MAIZE_PATCHES]
        grape = _compute_action_cost("plant", {"crop_key": "grape"}, prices, areas)
        assert grape == sum(PLANT_CHARGES["grape"]) == 499

    @pytest.mark.parametrize("crop", list(PLANT_CHARGES))
    def test_preview_prices_plant_as_action_does(
        self, client: TestClient, crop: str
    ) -> None:
        """AC3: preview == /action for each target, each pair on bare patches."""
        game_id, _ = _bare_default_field(client, crop)
        for patch_idx in (0, 1, 2, -1):
            params = {"crop_key": crop, "patch_idx": patch_idx}
            preview = _act(client, game_id, "plant", params, preview=True).json()
            executed = _act(client, game_id, "plant", params).json()
            assert preview["cost_credits"] == executed["cost_credits"], patch_idx
            _harvest_all(client, game_id)

    def test_preview_affordability_uses_the_area_scaled_cost(
        self, client: TestClient
    ) -> None:
        """AC3: 100 credits buy one patch of maize (67) but not all three (201)."""
        game_id, _ = _bare_default_field(client, "maize")
        games[game_id].ledger.balance_credits = 100
        one = _act(
            client, game_id, "plant", {"crop_key": "maize", "patch_idx": 0}, True
        )
        assert (one.json()["cost_credits"], one.json()["affordable"]) == (67, True)
        whole = _act(client, game_id, "plant", {"crop_key": "maize"}, preview=True)
        assert (whole.json()["cost_credits"], whole.json()["affordable"]) == (
            201,
            False,
        )
        assert _act(client, game_id, "plant", {"crop_key": "maize"}).status_code == 400

    @pytest.mark.parametrize("action", ["plant", "harvest"])
    @pytest.mark.parametrize("patch_idx", [3, 7])
    def test_out_of_range_preview_is_the_same_400_as_action(
        self, client: TestClient, action: str, patch_idx: int
    ) -> None:
        """AC3: an out-of-range preview used to price at 200 OK (#516)."""
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        params = {"crop_key": "maize", "patch_idx": patch_idx}
        preview = _act(client, game_id, action, params, preview=True)
        executed = _act(client, game_id, action, params)
        assert preview.status_code == executed.status_code == 400
        assert preview.json() == executed.json()


# ---------------------------------------------------------------------------
# Lime picker parity with prices.yaml (#631 B8)
# ---------------------------------------------------------------------------
class TestLimePickerParity:
    def test_lime_picker_matches_price_table(self, prices: PriceTable) -> None:
        source = _LIME_GD.read_text(encoding="utf-8")
        match = re.search(
            r"^const PRICE_PER_KG(?::\s*float)?\s*:?=\s*([\d.]+)$", source, re.M
        )
        assert match is not None
        assert float(match.group(1)) == prices.input_costs["amendment_lime_per_kg"]
        assert (
            _gd_int_const(source, "LABOR_PER_ACTION")
            == prices.input_costs["labor_per_action"]
        )


# ---------------------------------------------------------------------------
# Harvest receipt: settlements[] and date (#631 B1-B6)
# ---------------------------------------------------------------------------
def _check_receipt(body: dict, balance_before: int) -> dict:
    """The B2 identities every receipt must satisfy; returns the settlement."""
    assert len(body["settlements"]) == 1
    st = body["settlements"][0]
    assert abs(st["sold_kg_ha"] - st["dry_kg_ha"] / st["dry_matter_fraction"]) < 0.1
    assert abs(st["sold_kg"] - st["sold_kg_ha"] * st["area_ha"]) < 0.1
    assert abs(st["revenue_credits"] - st["sold_kg"] * st["price_credits_per_kg"]) < 1
    assert body["revenue_credits"] == st["revenue_credits"]
    assert body["balance_credits"] - balance_before == (
        st["revenue_credits"] - body["cost_credits"]
    )
    return dict(st)


class TestHarvestReceipt:
    def test_default_scenario_maize_receipt_across_two_seasons(
        self, client: TestClient
    ) -> None:
        game_id = _create_game(client, NL_MAIZE_PATCHES, credits=10_000)
        _step(client, game_id, 200)
        before = games[game_id].ledger.balance_credits
        body = _harvest(client, game_id, {"patch_idx": 1})
        assert body["date"] == "2024-10-18"
        st = _check_receipt(body, before)
        assert (st["crop_key"], st["product"], st["patch_indices"]) == (
            "maize",
            "grain",
            [1],
        )
        assert st["area_ha"] == 0.334
        assert (st["quarter"], st["base_credits_per_kg"]) == (4, 0.22)
        assert st["seasonal_multiplier"] == 1.2
        assert st["price_credits_per_kg"] == pytest.approx(0.264)
        assert st["dry_kg_ha"] > 0

        # Second season: replant the same patch, run on, harvest again. The
        # receipt describes this harvest only, not the first one.
        assert (
            _act(
                client, game_id, "plant", {"crop_key": "maize", "patch_idx": 1}
            ).status_code
            == 200
        )
        _step(client, game_id, 200)
        before2 = games[game_id].ledger.balance_credits
        body2 = _harvest(client, game_id, {"patch_idx": 1})
        st2 = _check_receipt(body2, before2)
        assert body2["date"] > body["date"]
        assert st2["patch_indices"] == [1]
        assert st2["revenue_credits"] != st["revenue_credits"]
        assert body2["revenue_credits"] == st2["revenue_credits"]

    def test_grape_receipt_uses_fresh_fruit(self, client: TestClient) -> None:
        game_id = _create_game(client, NL_MAIZE_PATCHES, credits=10_000)
        _harvest(client, game_id, {"patch_idx": 1})
        assert (
            _act(
                client, game_id, "plant", {"crop_key": "grape", "patch_idx": 1}
            ).status_code
            == 200
        )
        _step(client, game_id, 200)
        before = games[game_id].ledger.balance_credits
        body = _harvest(client, game_id, {"patch_idx": 1})
        st = _check_receipt(body, before)
        assert (st["product"], st["dry_matter_fraction"]) == ("fruit", 0.2528)
        assert (st["base_credits_per_kg"], st["seasonal_multiplier"]) == (0.8, 1.1)

    @pytest.mark.parametrize(
        ("days", "quarter", "multiplier"), [(182, 3, 0.8), (183, 4, 1.2)]
    )
    def test_quarter_boundary_kenya_maize(
        self, client: TestClient, days: int, quarter: int, multiplier: float
    ) -> None:
        patch = {
            "soil_profile_key": "loam_temperate",
            "crop_key": "maize",
            "climate_key": "kenya_highlands",
            "area_fraction": 1.0,
        }
        game_id = _create_game(client, [patch])
        _step(client, game_id, days)
        st = _harvest(client, game_id, {})["settlements"][0]
        assert (st["quarter"], st["seasonal_multiplier"]) == (quarter, multiplier)

    def test_full_field_harvest_is_one_settlement(self, client: TestClient) -> None:
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        _step(client, game_id, 200)
        body = _harvest(client, game_id, {})
        assert len(body["settlements"]) == 1
        st = body["settlements"][0]
        assert st["patch_indices"] == [0, 1, 2]
        assert st["area_ha"] == 1.0

    def test_irrigate_and_noop_have_no_settlements(self, client: TestClient) -> None:
        game_id = _create_game(client, NL_MAIZE_PATCHES)
        irrigate = _act(client, game_id, "irrigate", {"amount_mm": 10}).json()
        assert irrigate["settlements"] == []
        assert irrigate["date"] == games[game_id].current_date.isoformat()
        _harvest(client, game_id, {"patch_idx": 0})
        noop = _act(client, game_id, "harvest", {"patch_idx": 0}).json()
        assert noop["status"] == "no-op"
        assert noop["settlements"] == []
        assert noop["date"] == irrigate["date"]
