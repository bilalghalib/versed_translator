from versed_translator.benchmark.fable_export import stratified_sample


def test_stratified_sample_is_stable_and_excludes():
    items = []
    for source, n in [
        ("baladhuri_hitti", 20),
        ("ibn_khallikan_deslane", 12),
        ("hariri_assemblies", 10),
        ("blunt_odes", 8),
        ("miskawayh_eclipse", 5),
        ("ockley_hayy", 5),
    ]:
        for i in range(n):
            items.append({"id": f"{source}:x{i:03d}", "source": source})
    exclude = {"baladhuri_hitti:x000", "blunt_odes:x000"}
    a = stratified_sample(items, exclude_ids=exclude, seed=20260816)
    b = stratified_sample(items, exclude_ids=exclude, seed=20260816)
    assert a == b
    assert len(a) == 50
    assert "baladhuri_hitti:x000" not in a
    by_src: dict[str, int] = {}
    for item_id in a:
        src = item_id.split(":")[0]
        by_src[src] = by_src.get(src, 0) + 1
    assert by_src["baladhuri_hitti"] == 18
    assert by_src["blunt_odes"] == 6
