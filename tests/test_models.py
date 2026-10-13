from ltlsplitter.core.models import FretImport, FretRequirement


def _req(reqid, parent_reqid="") -> FretRequirement:
    return FretRequirement(reqid=reqid, fulltext="...", pt_formula=f"(H {reqid})", ft_formula=f"(G {reqid})", parent_reqid=parent_reqid)


def test_leaf_requirements_includes_unsplit_requirements():
    fi = FretImport(project="demo", requirements=[_req("r1"), _req("r2")])
    assert [r.reqid for r in fi.leaf_requirements()] == ["r1", "r2"]


def test_leaf_requirements_excludes_a_parent_in_favor_of_its_children():
    fi = FretImport(
        project="demo",
        requirements=[
            _req("r1"),
            _req("r1.1", parent_reqid="r1"),
            _req("r1.2", parent_reqid="r1"),
            _req("r2"),
        ],
    )
    assert [r.reqid for r in fi.leaf_requirements()] == ["r1.1", "r1.2", "r2"]


def test_leaf_requirements_handles_multiple_split_requirements_independently():
    fi = FretImport(
        project="demo",
        requirements=[
            _req("r1"),
            _req("r1.1", parent_reqid="r1"),
            _req("r2"),
            _req("r2.1", parent_reqid="r2"),
            _req("r2.2", parent_reqid="r2"),
        ],
    )
    assert [r.reqid for r in fi.leaf_requirements()] == ["r1.1", "r2.1", "r2.2"]
