import numpy as np
import pandas as pd
import pytest

from datascope import DataProfiler
from datascope.referential import alerts_for, key_stem, looks_like_key_name, name_suggests_reference


def _ri(result, column):
    return next(r for r in result["referential_integrity"] if r["column"] == column)


class TestNameRules:
    @pytest.mark.parametrize("name", ["id", "customer_id", "customerId", "ORDER_ID", "sku_code", "account_no", "parent_key"])
    def test_key_like_names(self, name):
        assert looks_like_key_name(name)

    @pytest.mark.parametrize("name", ["paid", "valid", "quantity", "android", "hybrid"])
    def test_words_merely_ending_in_id_are_not_keys(self, name):
        assert not looks_like_key_name(name)

    def test_stems(self):
        assert key_stem("customer_id") == "customer"
        assert key_stem("customerId") == "customer"
        assert key_stem("id") == ""

    def test_child_must_name_the_parent(self):
        assert name_suggests_reference("referred_by_customer_id", "customer_id")
        assert name_suggests_reference("manager_id", "id")
        assert not name_suggests_reference("order_id", "customer_id")   # different entity
        assert not name_suggests_reference("customer_id", "customer_id")  # itself
        assert not name_suggests_reference("customer_key", "customer_id")  # same entity, other key
        assert not name_suggests_reference("quantity", "id")


@pytest.fixture
def orders():
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({
        "order_id": np.arange(1, n + 1),
        "customer_id": rng.integers(1, 120, n),
        "parent_order_id": np.where(rng.random(n) < 0.4, rng.integers(1, n + 1, n), np.nan),
        "quantity": rng.integers(1, 6, n),   # small ints: trivially inside 1..n
        "status": rng.choice(["new", "paid", "shipped"], n),
    })
    df.loc[[3, 4], "parent_order_id"] = 7777
    return df


class TestDeclared:
    def test_other_table_series(self, orders):
        customers = pd.Series(np.arange(1, 101), name="customers.id")
        result = DataProfiler().profile(orders, references={"customer_id": customers})
        r = _ri(result, "customer_id")
        expected = orders["customer_id"] > 100
        assert (r["source"], r["same_table"], r["references"]) == ("declared", False, "customers.id")
        assert r["checked"] == len(orders)
        assert r["orphans"] == expected.sum()
        assert r["orphan_values"] == orders.loc[expected, "customer_id"].nunique()
        top = orders.loc[expected, "customer_id"].value_counts()
        assert r["sample_orphans"][0]["count"] == top.max()
        assert len(r["sample_orphans"]) <= 5

    def test_label_tuple_and_same_table_name(self, orders):
        result = DataProfiler(suggest_references=False).profile(orders, references={
            "customer_id": ("crm.customers.id", pd.Series(range(1, 1000))),
            "parent_order_id": "order_id",
        })
        assert _ri(result, "customer_id")["references"] == "crm.customers.id"
        r = _ri(result, "parent_order_id")
        assert r["same_table"] is True
        # NULLs are not orphans; only the two dangling 7777s are
        assert r["checked"] == orders["parent_order_id"].notna().sum()
        assert (r["orphans"], r["orphan_values"]) == (2, 1)
        assert r["sample_orphans"] == [{"value": "7777", "count": 2}]  # not "7777.0"

    def test_clean_reference_has_no_alert(self, orders):
        result = DataProfiler().profile(orders, references={"customer_id": pd.Series(range(1, 200), name="c.id")})
        assert _ri(result, "customer_id")["orphans"] == 0
        assert not [a for a in result["overview"]["alerts"] if a["column"] == "customer_id"]

    def test_numbers_vs_text_ids_are_compared_as_text(self):
        df = pd.DataFrame({"customer_id": [1, 2, 3, 4]})
        r = DataProfiler().profile(df, references={"customer_id": pd.Series(["1", "2", "3"], name="ref")})
        r = _ri(r, "customer_id")
        assert r["compared_as"] == "text" and r["orphans"] == 1 and r["sample_orphans"][0]["value"] == "4"

    def test_bad_declarations_fail_clearly(self, orders):
        with pytest.raises(ValueError, match="nope"):
            DataProfiler().profile(orders, references={"nope": "order_id"})
        with pytest.raises(ValueError, match="no column 'missing'"):
            DataProfiler().profile(orders, references={"customer_id": "missing"})
        with pytest.raises(TypeError):
            DataProfiler().profile(orders, references={"customer_id": [1, 2, 3]})

    def test_sensitive_child_values_are_masked(self):
        df = pd.DataFrame({"email": ["a@x.com", "b@x.com", "ghost@y.org"]})
        ref = pd.Series(["a@x.com", "b@x.com"], name="users.email")
        r = _ri(DataProfiler().profile(df, references={"email": ref}), "email")
        assert r["orphans"] == 1 and "ghost" not in r["sample_orphans"][0]["value"]

    def test_alert_severity(self):
        base = {"column": "c", "references": "p", "orphan_values": 1, "sample_orphans": []}
        sev = lambda **kw: alerts_for([{**base, **kw}])
        assert sev(source="declared", orphans=10, orphan_pct=20.0)[0]["severity"] == "high"
        assert sev(source="declared", orphans=1, orphan_pct=1.0)[0]["severity"] == "warning"
        assert sev(source="suggested", orphans=1, orphan_pct=1.0)[0]["severity"] == "warning"
        assert sev(source="declared", orphans=0, orphan_pct=0.0) == []


class TestSuggested:
    def test_named_self_reference_is_suggested_and_orphans_flagged(self, orders):
        result = DataProfiler().profile(orders)
        r = _ri(result, "parent_order_id")
        assert (r["source"], r["references"], r["orphans"]) == ("suggested", "order_id", 2)
        assert any(a["column"] == "parent_order_id" and "Looks like a reference" in a["message"]
                   for a in result["overview"]["alerts"])

    def test_no_false_positives_from_overlapping_integer_ranges(self, orders):
        # quantity (1..5) and customer_id (1..119) both sit inside order_id's
        # 1..300, but neither name points at order_id.
        cols = {r["column"] for r in DataProfiler().profile(orders)["referential_integrity"]}
        assert cols == {"parent_order_id"}

    def test_mostly_unmatched_is_not_a_reference(self):
        n = 200
        df = pd.DataFrame({"id": np.arange(1, n + 1), "legacy_id": np.arange(1, n + 1) + 150})
        assert DataProfiler().profile(df)["referential_integrity"] == []  # 75% "orphans": not a link

    def test_one_to_one_twin_key_is_not_suggested(self):
        df = pd.DataFrame({"id": np.arange(1, 101), "account_id": np.arange(1, 101)})
        assert DataProfiler().profile(df)["referential_integrity"] == []

    def test_declared_wins_over_suggested(self, orders):
        result = DataProfiler().profile(orders, references={"parent_order_id": "order_id"})
        assert [r["source"] for r in result["referential_integrity"]] == ["declared"]

    def test_can_be_turned_off(self, orders):
        assert DataProfiler(suggest_references=False).profile(orders)["referential_integrity"] == []


def test_cli_reference_to_another_file(tmp_path, monkeypatch, capsys):
    from datascope.cli import main

    pd.DataFrame({"customer_id": [1, 2, 3, 9], "amount": [5, 6, 7, 8]}).to_csv(tmp_path / "orders.csv", index=False)
    pd.DataFrame({"id": [1, 2, 3]}).to_csv(tmp_path / "customers.csv", index=False)
    out = tmp_path / "r.html"
    monkeypatch.setattr("sys.argv", ["datascope", str(tmp_path / "orders.csv"), "-o", str(out),
                                     "--reference", f"customer_id={tmp_path / 'customers.csv'}:id"])
    main()
    html = out.read_text(encoding="utf-8")
    parent = f"{tmp_path / 'customers.csv'}:id"
    assert f'"references": "{parent}"' in html and '"orphans": 1' in html
    # the label is the path as typed, so the printed command repeats the run
    assert f"--reference customer_id={parent}" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["datascope", str(tmp_path / "orders.csv"), "--reference", "customer_id"])
    with pytest.raises(SystemExit):
        main()
    assert "CHILD=PARENT" in capsys.readouterr().err
