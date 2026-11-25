from dataclasses import asdict

import dagster as dg

from src.dagster_pipeline.groups import STATIC_GROUP

from src.dagster_pipeline.assets.raw import (
    RAW_VG250_KEY,
    RAW_ZENSUS2022_POPULATION_KEY,
)
from src.ingestion.contract import GEOGRAPHY_VERSION
from src.database.normalize import refresh_hierarchy, refresh_population


NORMALIZED_HIERARCHY_KEY = dg.AssetKey(["normalized", "hierarchy"])
NORMALIZED_POPULATION_KEY = dg.AssetKey(["normalized", "population"])


@dg.asset(
    key=NORMALIZED_HIERARCHY_KEY,
    deps=[RAW_VG250_KEY],
    group_name=STATIC_GROUP,
    description=(
        "normalized.land, kreis and gemeinde: VG250 land parts "
        "(GF = 4) with parent keys, EPSG:3035 geometry and area."
    ),
)
def normalized_hierarchy(context: dg.AssetExecutionContext) -> None:
    summary = refresh_hierarchy()
    context.add_output_metadata(
        {"geography_version": GEOGRAPHY_VERSION, **asdict(summary)}
    )


@dg.asset(
    key=NORMALIZED_POPULATION_KEY,
    deps=[NORMALIZED_HIERARCHY_KEY, RAW_ZENSUS2022_POPULATION_KEY],
    group_name=STATIC_GROUP,
    description=(
        "normalized.gemeinde_population (Zensus 2022 total population "
        "per Gemeinde; NULL with an explicit status, never 0, when there is "
        "no census record) and zensus_published_population (published "
        "Bund/Land/Kreis/Gemeinde totals for source checks)."
    ),
)
def normalized_population(context: dg.AssetExecutionContext) -> None:
    summary = refresh_population()
    context.add_output_metadata(
        {"geography_version": GEOGRAPHY_VERSION, **asdict(summary)}
    )


NORMALIZED_ASSETS = [
    normalized_hierarchy,
    normalized_population,
]
