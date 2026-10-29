"""Повторно создаёт включённый пример на реальных данных, если доступен Overpass."""
# Path builds output paths relative to this script, so running it from another folder still works.
from pathlib import Path

# Settings configures the planting plan; analyze loads map data and calculates candidates and metrics.
from core.optimizer import Settings
# analyze получает данные карты и выполняет весь расчёт кандидатов, планов и метрик.
from core.pipeline import analyze
# Export helpers write the same analysis in formats the app and spreadsheet/GIS tools can open.
from services.export import save_csv, save_geojson, save_map_png, save_scenario


# Точка входа генератора создаёт полный пример для района Алматы и сохраняет его в несколько форматов.
def main() -> None:
    # Bounding box around central Almaty: (south latitude, west longitude, north latitude, east longitude), degrees.
    bounds=(43.2353,76.8848,43.2425,76.8946)
    # Analyze the area with a 20-tree target, 200,000 total budget, 10,000 per tree and reproducible seed 42.
    analysis=analyze(bounds,Settings(trees=20,budget=200000,cost_per_tree=10000,seed=42))
    # Put generated files in examples/almaty beside the project example data.
    folder=Path(__file__).resolve().parent/"almaty"
    # Create the output directory and any missing parents; do nothing if it already exists.
    folder.mkdir(parents=True,exist_ok=True)
    # Use a shared base name for the JSON scenario and its GeoJSON/CSV companions.
    base=folder/"almaty_center.json"
    # Save full scenario data, including candidates, settings, both plans, metrics, map layers and walking routes.
    save_scenario(base,analysis.bounds,analysis.candidates,analysis.settings,analysis.greedy,
                  # Передаём второй план и все дополнительные пространственные данные для полного повторного открытия сценария.
                  analysis.random,analysis.metrics,analysis.layers,analysis.free_layer,analysis.route_lines)
    # Save selected candidates with geographic geometries for GIS software.
    save_geojson(base.with_suffix(".geojson"),analysis.candidates,analysis.greedy)
    # Save candidates and selection flags as a spreadsheet-friendly CSV table.
    save_csv(base.with_suffix(".csv"),analysis.candidates,analysis.greedy)
    # Add the computed free-space geometry to the map layers for the before/after pictures.
    layers={**analysis.layers,"free":analysis.free_layer}
    # The before image has no selected tree ids, so it shows the starting map and available candidates.
    save_map_png(folder/"before.png",bounds,layers,analysis.candidates,[])
    # The after image highlights the ids selected by the greedy optimizer.
    save_map_png(folder/"after.png",bounds,layers,analysis.candidates,analysis.greedy.ids)
    # Print candidate and chosen-tree counts so a person running the script can quickly see its outcome.
    print(f"OSM candidates: {len(analysis.candidates)}; selected trees: {len(analysis.greedy.ids)}")
    # Print all computed metrics, including comparisons and any model limitations.
    print(analysis.metrics)


# __name__ is "__main__" only when this file is run directly, not when imported by another module.
if __name__=="__main__":
    # Run the generation pipeline only for direct execution of this script.
    main()
