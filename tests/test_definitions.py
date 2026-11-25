"""The Dagster definitions: one asset group per theme, each run by its jobs,
and every check registered."""

from src.dagster_pipeline.definitions import defs


GROUPS = {
    "static": {
        "raw/icon_grid",
        "normalized/icon_cell",
        "raw/vg250",
        "raw/zensus2022_population",
        "normalized/hierarchy",
        "normalized/population",
        "normalized/icon_gemeinde_bridge",
    },
    "forecast": {
        "raw_icon_t_2m",
        "raw_icon_relhum_2m",
        "raw_icon_u_10m",
        "raw_icon_v_10m",
        "normalized/gemeinde_forecast",
        "analytical/current_forecast_25h",
    },
    "employment": {"raw/ba_gemeindedaten", "normalized/indicator_value"},
    "sectors": {"raw/ba_regionalreport", "raw/ba_wz_heft", "normalized/sector_values"},
}
JOBS = {
    "static": ("static",),
    "forecast": ("forecast", "forecast_publish"),
    "employment": ("employment",),
    "sectors": ("sectors",),
}
CHECKS = {
    "icon_cell_geometry_quality",
    "vg250_source_contract",
    "zensus2022_population_source_contract",
    "key_coverage",
    "hierarchy_integrity",
    "source_totals",
    "bridge_coverage",
    "forecast_completeness",
    "forecast_plausibility",
    "ba_source_contract",
    "ba_column_identities",
    "ba_key_coverage",
    "ba_source_totals",
    "ba_sector_source_contract",
    "ba_sector_identities",
    "ba_sector_source_totals",
    "ba_sector_key_coverage",
}


def test_each_group_holds_one_theme_and_its_jobs_run_exactly_it() -> None:
    graph = defs.resolve_asset_graph()
    groups: dict[str, set[str]] = {}
    for key in graph.get_all_asset_keys():
        groups.setdefault(graph.get(key).group_name, set()).add(key.to_user_string())
    assert groups == GROUPS

    for group, job_names in JOBS.items():
        selected = set()
        for name in job_names:
            job = defs.resolve_job_def(name)
            selected |= {key.to_user_string() for key in job.asset_layer.selected_asset_keys}
        assert selected == GROUPS[group], group


def test_all_checks_are_registered() -> None:
    graph = defs.resolve_asset_graph()
    assert {key.name for key in graph.asset_check_keys} == CHECKS
